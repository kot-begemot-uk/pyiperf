#!/usr/bin/python3
'''Iperf external helper'''

# pyiperf, Copyright (c) 2023 RedHat Inc
# pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

# This source code is licensed under both the BSD-style license (found in the
# LICENSE file in the root directory of this source tree) and the GPLv2 (found
# in the COPYING file in the root directory of this source tree).
# You may select, at your option, one of the above-listed licenses.

import struct
import socket
import time
import threading
import psutil
from iperf_utils import json_send, json_recv, make_cookie
from iperf_data import UDPClient, TCPClient
from iperf_data_plugin import PluginClient

#IPERF FSM STATES

TEST_START = 1
TEST_RUNNING = 2
RESULT_REQUEST = 3
TEST_END = 4
STREAM_BEGIN = 5
STREAM_RUNNING = 6
STREAM_END = 7
ALL_STREAMS_END = 8
PARAM_EXCHANGE = 9
CREATE_STREAMS = 10
SERVER_TERMINATE = 11
CLIENT_TERMINATE = 12
EXCHANGE_RESULTS = 13
DISPLAY_RESULTS = 14
IPERF_START = 15
IPERF_DONE = 16
ACCESS_DENIED = -1
SERVER_ERROR = -2

STATE = "b"

class TestClient():
    '''Iperf3 compatible test client'''

    def __init__(self, config, params):

    # test protocol "tcp", "udp", "sctp"
    # "omit" (TODO)
    # "server_affinity" (TODO)
    # "time" test duration in seconds
    # "num" test bytes or zero for no limit
    # "blockcount" test blocks or zero for no limit
    # "MSS" MSS for TCP - TODO
    # "nodelay" TCP nodelay - TODO
    # "parallel" number of streams in parallel
    # "reverse" test TODO
    # "bidirectional" test TODO
    # "window" buffer size for TCP (TODO)
    # "len" block length
    # "bandwidth" (TODO)
    # "fqrate" fqrate ???
    # "pacing_timer" socket TX pacing timer
    # "burst" - allowed burst
    # "TOS" - TODO
    # "flowlabel" v6 flowlabel
    # "title" test title
    # "extra_data" extra data ???
    # "congestion" TCP congestion control algo. TODO
    # "congestion_used" actual congestion used
    # "get_server_output" get output from server to display on client
    # "udp_counters_64bit" 64 bit packet counters
    # "repeating_payload" payload to repeat
    # "zerocopy" use sendfile if available
    # "dont_fragment" do not fragment flag

        self.params = params
        self.config = config
        self.state = 0
        self.ctrl_sock = None
        self.tx_streams = []
        self.result = None
        self.cpu_usage = None
        self.results = None
        self.peer_result = None
        self.test_ended = False
        self.timers = {}
        self.server = False
        self.needs_display = True
        self.start_time = None

    def send_parameters(self):
        '''Exchange Test Params'''
        return json_send(self.ctrl_sock, self.params)

    def collate_results(self):
        '''TX results'''
        self.results = {}
        cpu_usage = psutil.Process().cpu_times()
        self.results["cpu_util_system"] = cpu_usage.system - self.cpu_usage.system
        self.results["cpu_util_user"] = cpu_usage.user - self.cpu_usage.user
        self.results["cpu_util_total"] = self.results["cpu_util_user"] + self.results["cpu_util_system"]
        self.results["sender_has_retransmits"] = 0
        self.results["streams"] = []


        for stream in self.tx_streams:
            stream.lock.acquire()
            self.results["streams"].append(stream.result)
            stream.lock.release()
            stream.shutdown()

    def display_results(self):
        '''Display results'''
        if self.needs_display:
            self.needs_display = False
            print("My result {}".format(self.results))
            print("Peer result {}".format(self.peer_result))

    def exchange_results(self):
        '''Exchange results at the end of test'''
        self.collate_results()
        if self.server:
            self.peer_result = json_recv(self.ctrl_sock)
            json_send(self.ctrl_sock, self.results)
            return True
        if json_send(self.ctrl_sock, self.results):
            self.peer_result = json_recv(self.ctrl_sock)
            return True
        return False

    def create_streams(self):
        '''Create Stream'''
        if self.params.get("udp") is not None and self.ctrl_sock is not None:
            self.params["MSS"] = self.ctrl_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG)
        off = 1
        for stream_id in range(self.params["parallel"]):
            # This is a bug in iperf. It numbers treams in the following ingenious way
            # 1 3 4...
            if stream_id == 1:
                off = 2
            if self.config.get("plugin") is not None:
                self.tx_streams.append(PluginClient(self.config, self.params, stream_id + off))
            else:
                if self.params.get("udp") is not None:
                    self.tx_streams.append(UDPClient(self.config, self.params, stream_id + off))
                if self.params.get("tcp") is not None:
                    self.tx_streams.append(TCPClient(self.config, self.params, stream_id + off))
        for stream in self.tx_streams:
            stream.connect()
        return True

    def start_test(self):
        '''Start Stream'''
        self.cpu_usage = psutil.Process().cpu_times()
        self.start_time = time.time()

        self.timers["end"] = threading.Timer(self.params["time"], self.end_test_timer)
        self.timers["end"].start()
        self.timers["failsafe"] = threading.Timer(self.params["time"] + 10, self.end_test_failsafe)
        self.timers["failsafe"].start()

        for stream in self.tx_streams:
            stream.start()

        return True

    def end_test_timer(self):
        '''Timer to end the test'''
        self.timers["end"] = None
        if self.config["compat"] == 1 and not self.server:
            try:
                self.ctrl_sock.send(struct.pack(STATE, TEST_END))
            except OSError:
                pass
            except AttributeError:
                pass

    def end_test_failsafe(self):
        '''Failsafe - length + 10 seconds'''
        self.timers["failsafe"] = None
        self.state_transition(DISPLAY_RESULTS)


    def end_test(self):
        '''Finish Test and clean up'''
        if self.test_ended:
            return True
        if self.ctrl_sock is not None:
            self.ctrl_sock.close()
        if self.timers.get("end") is not None:
            self.timers["end"].cancel()
        if self.timers.get("failsafe") is not None:
            self.timers["failsafe"].cancel()
        self.test_ended = True
        return False

    def connect(self):
        '''Connect to server'''
        self.ctrl_sock = socket.socket() # defaults to AF_INET/STREAM
        self.ctrl_sock.connect((self.config["target"], self.config["config_port"]))

    def state_transition(self, new_state):
        '''Transition iperf state'''

        self.state = new_state
        result = False

        if new_state == PARAM_EXCHANGE:
            result = self.send_parameters()
        elif new_state == CREATE_STREAMS:
            result = self.create_streams()
        elif new_state == TEST_START:
            result = self.start_test()
        elif new_state == TEST_RUNNING:
            result = True
        elif new_state == EXCHANGE_RESULTS:
            result = self.exchange_results()
        elif new_state == DISPLAY_RESULTS:
            self.display_results()
            result = self.end_test()
        elif new_state == IPERF_DONE:
            result =  True
        elif new_state == SERVER_TERMINATE:
            self.state_transition(DISPLAY_RESULTS)
            self.state = IPERF_DONE
            result = True
        elif new_state == ACCESS_DENIED:
            result = False
        elif new_state == SERVER_ERROR:
            result =  True # for now TODO - read error code and make sense of it

        return result

    def authorize(self):
        '''Perform initial handshake'''
        self.ctrl_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.config["cookie"] = make_cookie()
        self.ctrl_sock.send(self.config["cookie"])
        if self.params.get("MSS") is not None:
            return

    def run(self):
        '''Run the client'''

        self.connect()
        self.authorize()
        try:
            while True:
                data = self.ctrl_sock.recv(1)
                self.state_transition(struct.unpack(STATE, data)[0])
        except struct.error:
            self.state_transition(DISPLAY_RESULTS)
        except OSError:
            self.state_transition(DISPLAY_RESULTS)
        except KeyboardInterrupt:
            self.state_transition(DISPLAY_RESULTS)
        self.end_test()
