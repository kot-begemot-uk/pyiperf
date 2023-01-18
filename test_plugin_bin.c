/*
* pyiperf, Copyright (c) 2023 RedHat Inc
* pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

* This source code is licensed under both the BSD-style license (found in the
* LICENSE file in the root directory of this source tree) and the GPLv2 (found
* in the COPYING file in the root directory of this source tree).
* You may select, at your option, one of the above-listed licenses.
*/

#include <sys/socket.h>
#include <sys/un.h>
#include <string.h>
#include <stdio.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <math.h>
#include <stdbool.h>
#include <errno.h>
#include <arpa/inet.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>



#include <jansson.h>

/* Receive JSON data */

static timer_t end_timer;
static timer_t failsafe_timer;
static timer_t report_timer;

static bool running = true;
static bool report_needed = false;
static bool packets64 = false;
static bool do_header = false;
static char *buffer;

#define END_TIMER 0
#define FAILSAFE_TIMER 1
#define REPORT_TIMER 2

static int l, s, d;
static int bufsize;
static long long bytes_sent;
static long long packets_sent;

struct header32 {
    u_int32_t sec, usec, counter;
};

struct header64 {
    u_int32_t sec, usec;
    u_int64_t counter;
};

static json_t * json_recv(int s)
{
    u_int32_t size;
    int ret, so_far;
    char *text;
    json_t *result;

    ret = recv(s, &size, sizeof(u_int32_t), 0);
    if (ret < 0) {
        perror("Failed to read JSON size");
        return NULL;
    }
    size = ntohl(size);
    text = malloc(size + 1);
    memset(text, 0, size + 1);
    so_far = 0;
    while (so_far < size) {
        ret = recv(s, text + so_far, size - so_far, 0);
        if (ret < 0) {
            perror("Failed to read JSON data");
            free(text);
            return NULL;
        }
        so_far += ret;
    }
    result = json_loads(text, JSON_DECODE_ANY, NULL);
    free(text);
    return result;
}

/* Send JSON data */

static int json_send(int s, json_t *data)
{
    u_int32_t size, s_size;
    int ret, so_far;
    char *text;

    text = json_dumps(data, 0);
    if (text == NULL) {
        return -1;
    }
    size = strlen(text);
    s_size = htonl(size);
    ret = send(s, &s_size, sizeof(u_int32_t), 0);
    if (ret < 0) {
        perror("Failed to send JSON size");
        return -1;
    }
    so_far = 0;
    while (so_far < size) {
        ret = send(s, text + so_far, size - so_far, 0);
        if (ret < 0) {
            perror("Failed to send JSON data");
            free(text);
            return -1;
        }
        so_far += ret;
    }
    free(text);
    return 0;
}



static void do_stats_and_header(void *header)
{
    struct timespec ts;
    struct header32 *h32 = (struct header32 *) header;
    struct header64 *h64 = (struct header64 *) header;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) {
        h32->sec = htonl(ts.tv_sec);
        h32->usec = htonl(ts.tv_nsec / 1000);
    }
    if (packets64) {
        h64->counter = htobe64(packets_sent);
    } else {
        h32->counter = htonl(packets_sent);
    }
}

double start_time;

static double time_now(void)
{
    double result = 0.0;
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
        result = ts.tv_sec + ts.tv_nsec / 1000000000;
    }
    return result;
}


static void produce_report(bool final)
{
    json_t *report;
    json_error_t error;
    double bytes_temp = bytes_sent * 1.0;
    double packets_temp = packets_sent * 1.0;

    fprintf(stderr, "creating a report %d\n", final); 

    report = json_pack_ex(&error, 0, "{s:f, s:i, s:f, s:i, s:f, s:f, s:f, s:b}",
                       "bytes", bytes_temp, //s:f
                       "retransmits", 0, //s:i
                       "jitter", 0.0, //s:f
                       "errors", 0, //s:i
                       "packets", packets_temp, //s:f
                       "start_time", 0.0, //s:f
                       "end_time", time_now() - start_time, //s:f
                       "final", final); //s:b
    if (report == NULL) {
        fprintf(stderr, 
                "Failed to generate a report %s %s %d %d %d\n",
                error.text, error.source, error.line, error.column, error.position);
    } else {
        fprintf(stderr, "report:"); 
        json_dumpf(report, stderr, 0);
        fprintf(stderr, "\n"); 
    }
    if (json_send(s, report) != 0) {
        fprintf(stderr, "failed to send report\n"); 
    }
    json_object_clear(report);
    free(report);
}

static void send_data(int d)
{
    int ret;
    start_time = time_now();
    while (running) {
        if (do_header) {
            do_stats_and_header(buffer);
        }
        ret = send(d, buffer, bufsize, 0);
        if (ret > 0) {
            bytes_sent += ret;
            packets_sent ++;
        } else {
            if (errno != EAGAIN)
                break;
        }
        if (report_needed) {
            produce_report(false);
            report_needed = false;
        }
    }
    /* Produce final report regardless of "needed" flag */
    produce_report(true);
}

#define COOKIE_SIZE 37

static int connect_test(json_t *config, json_t *params)
{
    struct addrinfo hints, *target;
    char portstr[6];
    int gerror, ret = -1;
    json_t *mss;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;

    if (json_object_get(params, "version6")) {
        hints.ai_family = AF_INET6;
    }
    if (json_object_get(params, "version4")) {
        hints.ai_family = AF_INET;
    }

    if (json_object_get(params, "udp")) {
        hints.ai_socktype = SOCK_DGRAM;
        do_header = true;
    } else {
        hints.ai_socktype = SOCK_STREAM;
    }

    snprintf(portstr, sizeof(portstr), "%d", json_integer_value(json_object_get(config, "data_port")));

    if ((gerror = getaddrinfo(json_string_value(json_object_get(config, "target")), portstr, &hints, &target)) != 0) {
        perror("Failed to resolve target");
        return -1;
    }
    ret = socket(target->ai_family, hints.ai_socktype, 0);
    if (connect(ret, (struct sockaddr *) target->ai_addr, target->ai_addrlen) < 0) {
        perror("Failed to connect");
        freeaddrinfo(target);
        return -1;
    }

    freeaddrinfo(target);

    if (json_object_get(params, "udp")) {
        u_int64_t udp_connect = 0x36373839;
        send(ret, &udp_connect, sizeof(udp_connect), 0);
    } else {
        int i;
        char cookie[COOKIE_SIZE + 1];
        char buff[3];
        const char *str_cookie = json_string_value(json_object_get(config, "cookie"));
        /* we receive the cookie hexed and we need to unhex it*/
        if (strlen(str_cookie) < COOKIE_SIZE * 2) {
            return -1;
        }
        buff[2] = 0;
        for (i = 0; i < COOKIE_SIZE; i++) {
            memcpy(&buff, str_cookie + i*2, 2);
            cookie[i] = strtoul((char *)&buff, NULL, 16);
        }
        send(ret, &cookie, COOKIE_SIZE, 0);
    }
    mss = json_object_get(config, "MSS");
    if (mss == NULL) {
        mss = json_object_get(config, "len");
    }
    if (mss == NULL) {
        bufsize = 8192;
    } else {
        bufsize = json_integer_value(mss);
    }
    buffer = malloc(bufsize);
    return ret;
}

static void handler(int sig, siginfo_t *si, void *uc)
{
    switch (si->si_value.sival_int) {
        case END_TIMER:
            running = false;
            break;
        case FAILSAFE_TIMER:
            fprintf(stderr, "Failsafe timer\n");
            exit(1); /* brutal, but if we reached this point - who cares */
            break;
        case REPORT_TIMER:
            report_needed = true;
            break;
    }
}


static int create_timers(json_t *config, json_t *params)
{
    json_t *value;
    struct sigevent sev;
    double timer_value;
    struct itimerspec its;
    struct sigaction sa;
    sigset_t mask;

    sigemptyset(&mask);
    sigaddset(&mask, SIGPIPE);
    if (sigprocmask(SIG_BLOCK, &mask, NULL) == -1) {
        perror("Sigprocmask ");
        return -1;
    }

    sigemptyset(&mask);
    sa.sa_flags = SA_SIGINFO;
    sa.sa_sigaction = handler;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGALRM, &sa, NULL) == -1) {
        perror("Sigaction ");
        return -1;
    }

    sigemptyset(&mask);
    sigaddset(&mask, SIGALRM);
    if (sigprocmask(SIG_UNBLOCK, &mask, NULL) == -1) {
        perror("Sigprocmask ");
        return -1;
    }

    sev.sigev_notify = SIGEV_SIGNAL;
    sev.sigev_signo = SIGALRM;
    sev.sigev_value.sival_int = END_TIMER;

    value = json_object_get(params, "time");
    if (value == NULL) {
        fprintf(stderr, "Failed to get test time\n");
        return -1;
    }
    if (json_is_integer(value)) {
        timer_value = json_integer_value(value) * 1.0;
    } else {
        timer_value = json_real_value(value);
    }
    if (timer_create(CLOCK_MONOTONIC, &sev, &end_timer) < 0) {
        perror("End timer create");
        return -1;
    } 

    its.it_value.tv_sec = (int) timer_value;
    its.it_value.tv_nsec = (int)((timer_value - its.it_value.tv_sec) * 1000000000.0);
    its.it_interval.tv_sec = 0;
    its.it_interval.tv_nsec = 0;
    if (timer_settime(end_timer, 0, &its, NULL) == -1) { 
        perror("End timer set");
        return -1;
    } 

    sev.sigev_notify = SIGEV_SIGNAL;
    sev.sigev_signo = SIGALRM;
    sev.sigev_value.sival_int = FAILSAFE_TIMER;

    if (timer_create(CLOCK_MONOTONIC, &sev, &failsafe_timer) < 0) {
        perror("Failsafe timer create");
        return -1;
    }

    its.it_value.tv_sec = (int) timer_value;
    its.it_value.tv_nsec = (int)((timer_value - its.it_value.tv_sec) * 1000000000.0);
    its.it_value.tv_sec += 10;
    its.it_interval.tv_sec = 0;
    its.it_interval.tv_nsec = 0;
    if (timer_settime(failsafe_timer, 0, &its, NULL) == -1) { 
        perror("Failsafe timer set");
        return -1;
    } 


    value = json_object_get(config, "interval");
    if (value == NULL) {
        fprintf(stderr, "Failed to get reporting interval\n");
        return -1;
    }
    if (json_is_integer(value)) {
        timer_value = json_integer_value(value) * 1.0;
    } else {
        timer_value = json_real_value(value);
    }

    sev.sigev_notify = SIGEV_SIGNAL;
    sev.sigev_signo = SIGALRM;
    sev.sigev_value.sival_int = REPORT_TIMER;

    if (timer_create(CLOCK_MONOTONIC, &sev, &report_timer) < 0) {
        perror("Report timer create ");
        return -1;
    }

    its.it_value.tv_sec = its.it_interval.tv_sec = (int) timer_value;
    its.it_value.tv_nsec = its.it_interval.tv_nsec = (int)((timer_value - its.it_value.tv_sec) * 1000000000.0);


    if (timer_settime(report_timer, 0, &its, NULL) == -1) { 
        perror("Report timer set ");
        return -1;
    } 
    return 0;
}
 
static void cleanup(void)
{
    sigset_t mask;

    sigemptyset(&mask);
    sigprocmask(SIG_SETMASK, &mask, NULL);
    if (l)
        close(l);
    if (s)
        close(s);
    if (report_timer)
        timer_delete(report_timer);
    if (end_timer)
        timer_delete(end_timer);
    if (failsafe_timer)
        timer_delete(failsafe_timer);
    if (l)
        close(l);
    if (s)
        close(s);
    if (d)
        close(d);
}

int main(int argc, char *argv[])
{
    struct sockaddr_un sock, rsock;
    int rsize;

    json_t *config, *params;
    char state;

    if(argc != 2)
    {
        fprintf(stderr, "usage: %s listening socket\n\n", argv[0]);
        return 2;
    }

    strncpy((char *) &sock.sun_path, argv[1], 108);
    sock.sun_family = AF_UNIX;
    l = socket(AF_UNIX, SOCK_STREAM, 0);
    if (l < 0) {
        perror("Failed to allocate listening socket");
        exit(2);
    }
    if (bind(l, (const struct sockaddr*) &sock, sizeof(struct sockaddr_un)) < 0) {
        perror("Failed to bind listening socket");
        exit(2);
    }
    listen(l, 64);
    s = accept(l, (struct sockaddr*) &rsock, &rsize);
    if (s < 0) {
        fprintf(stderr, "Accept failed");
        cleanup();
        exit(2);
    }
    config = json_recv(s);
    if (config == NULL) {
        fprintf(stderr, "\nFailed to receive config\n");
        exit(2);
    }
    params = json_recv(s);
    if (params == NULL) {
        fprintf(stderr, "\nFailed to receive params\n");
        exit(2);
    }
    d = connect_test(config, params);
    if (d < 0) {
        fprintf(stderr, "Failed to connect");
        cleanup();
        exit(2);
    }
    if (recv(s, &state, 1, 0) != 1) {
        fprintf(stderr, "Failed to receive test start indication");
        cleanup();
        exit(2);
    } else {
        fprintf(stderr, "Starting test");
    }
    if (create_timers(config, params) < 0) {
        fprintf(stderr, "Failed to create timers");
        cleanup();
        exit(2);
    } else {
        fprintf(stderr, "Created Timers\n");
    }
    send_data(d);
    cleanup();
}
    
