#!/usr/bin/python3

''' iperf3+ compatible python client
'''

#
# Copyright (c) 2022 Red Hat, Inc., Anton Ivanov <anivanov@redhat.com>
# Copyright (c) 2022 Cambridge Greys Ltd <anton.ivanov@cambridgegreys.com>
#
# Dual Licensed under the GNU Public License Version 2.0 and BSD 3-clause
#
#

from argparse import ArgumentParser
import json
import sys
from iperf_control import TestClient
from iperf_control_server import TestServer

DEFAULT_CONFIG = "config-stock.json"
DEFAULT_PARAMS = "params.json"
NOT_SUPPORTED = "Not yet supported, use stock iperf3"

UNSUPPORTED = [
    'format', 'pidfile', 'file', 'affinity', 'bind', 'bind_dev',
    'logfile', 'forceflush', 'timestamps', 'daemon', 'one_off', 'server_bitrate_limit',
    'idle_timeout', 'rsa_private_key_path', 'authorized_users_path', 'time_skew_threshold',
    'pacing_timer', 'fq_rate', 'bytes', 'blockcount', 'length', 'congestion',
    'no_delay', 'version4', 'version6', 'tos', 'dscp', 'flowlabel', 'zerocopy',
    'omit', 'title', 'extra_data', 'get_server_output', 'udp_counters_64bit',
    'repeating_payload', 'dont_fragment', 'username', 'rsa_public_key_path'
]

def main():

    '''Run pyiperf'''

    aparser = ArgumentParser(description=main.__doc__)
    aparser.add_argument(
        '--config',
        help='config file in json format',
        type=str,
        default=DEFAULT_CONFIG)

    aparser.add_argument(
        '--params',
        help='iperf3 params file in json format',
        type=str,
        default=DEFAULT_PARAMS)

    aparser.add_argument(
        '-p', '--port',
        help='server port to listen on/connect to',
        type=int)

    aparser.add_argument(
        '-f', '--format',
        help='[kmgtKMGT] format to report: Kbits, Mbits, Gbits, Tbits',
        type=str)

    aparser.add_argument(
        '-i', '--interval',
        help='seconds between periodic throughput reports',
        type=int,
        default=1)

    aparser.add_argument(
        '-I', '--pidfile',
        help='write PID file',
        type=str)

    aparser.add_argument(
        '-F', '--file',
        help='xmit/recv the specified file',
        type=str)

    aparser.add_argument(
        '-A', '--affinity',
        help='set CPU affinity',
        type=str)

    aparser.add_argument(
        '-B', '--bind',
        help='host[%%dev] bind to the interface associated with the address <host> (optional <dev> equivalent to --bind-dev <dev>',
        type=str)

    aparser.add_argument(
        '--bind-dev',
        help='bind to device',
        type=str)

    aparser.add_argument(
        '-V', '--verbose',
        help='more detailed output',
        action='store_true')

    aparser.add_argument(
        '-J', '--json',
        help='output in json format',
        action='store_true')

    aparser.add_argument(
        '--logfile',
        help='send output to a log file',
        type=str)

    aparser.add_argument(
        '--forceflush',
        help='force flushing output at every interval',
        action='store_true')

    aparser.add_argument(
        '--timestamps',
        help='emit a timestamp at the start of each output line',
        action='store_true')

    aparser.add_argument(
        '--rcv-timeout',
        help='idle timeout for receiving data (default 120000 ms)',
        type=int,
        default=120000)

    aparser.add_argument(
        '--snd-timeout',
        help='timeout for unacknowledged TCP data (default 120000 ms)',
        type=int,
        default=120000)

    aparser.add_argument(
        '-d', '--debug',
        help='emit debugging output',
        action='store_true')

    aparser.add_argument(
        '-v', '--version',
        help='show version information and quit',
        action='store_true')

    aparser.add_argument(
        '-s', '--server',
        help='run in server mode',
        action='store_true')

    aparser.add_argument(
        '-D', '--daemon',
        help='run the server as a daemon',
        action='store_true')

    aparser.add_argument(
        '-1', '--one-off',
        help='handle one connection and exit',
        action='store_true')

    aparser.add_argument(
        '--server-bitrate-limit',
        help='server\'s total bit rate limit (default 0 = no limit)',
        type=int)

    aparser.add_argument(
        '--idle-timeout',
        help='restart idle server after # seconds in case it got stuck (default - no timeout)',
        type=int,
        default=0)

    aparser.add_argument(
        '--rsa-private-key-path',
        help='path to the RSA private key used to decrypt authentication credentials',
        type=str)

    aparser.add_argument(
        '--authorized-users-path',
        help='path to the configuration file containing user credentials',
        type=str)

    aparser.add_argument(
        '--time-skew-threshold',
        help='time skew threshold (in seconds) between the server and client during the authentication process',
        type=int)

    aparser.add_argument(
        '-c', '--client',
        help='run in client mode, connecting to <host> (option <dev> equivalent to `--bind-dev <dev>`)',
        type=str)

    aparser.add_argument(
        '-u', '--udp',
        help='use UDP instead of TCP',
        type=str)

    aparser.add_argument(
        '--connect-timeout',
        help='timeout for control connection setup ms',
        type=int)

    aparser.add_argument(
        '--bitrate',
        help='target bitrate in bits/sec. Default - 1Mb/s UDP, unlimited for TCP',
        type=int)

    aparser.add_argument(
        '--pacing-timer',
        help='set the timing for pacing in ms. Default - 1000',
        type=int)

    aparser.add_argument(
        '--fq-rate',
        help='enable fair-queueing based socket pacing, bits/sec',
        type=int)

    aparser.add_argument(
        '-t', '--time',
        help='time in seconds to transmit, default - 10s',
        type=int,
        default=10)

    aparser.add_argument(
        '-n', '--bytes',
        help='number of bytes to transmit (instead of -t)',
        type=int)

    aparser.add_argument(
        '-k', '--blockcount',
        help='number of blocks (packets) to transmit (instead of -t or -n)',
        type=int)

    aparser.add_argument(
        '-l', '--length',
        help='length of buffer to read or write - default 128KB for TCP, dynamic for UDP',
        type=int)

    aparser.add_argument(
        '--cport',
        help='bind to a specific client port (TCP and UDP, default: ephemeral port)',
        type=int)

    aparser.add_argument(
        '-P', '--parallel',
        help='number of parallel client streams to run',
        type=int,
        default=1)

    aparser.add_argument(
        '-R', '--reverse',
        help='run in reverse mode (server sends, client receives)',
        action='store_true')

    aparser.add_argument(
        '--bidir',
        help='run in bidirectional mode.  Client and server send and receive data.',
        action='store_true')

    aparser.add_argument(
        '-w', '--window',
        help='set send/receive socket buffer size',
        type=int)

    aparser.add_argument(
        '-C', '--congestion',
        help='set TCP congestion control algorithm',
        type=str)

    aparser.add_argument(
        '-M', '--set-mss',
        help='set TCP/SCTP maximum segmet size',
        type=int)

    aparser.add_argument(
        '-N', '--no-delay',
        help='set TCP/SCTP no delay, disable Nagle\'s algorithm',
        action='store_true')

    aparser.add_argument(
        '-4', '--version4',
        help='only use IPv4',
        action='store_true')

    aparser.add_argument(
        '-6', '--version6',
        help='only use IPv6',
        action='store_true')

    aparser.add_argument(
        '-S', '--tos',
        help='set the IP type of service 0-255',
        type=int)

    aparser.add_argument(
        '--dscp',
        help='set the IP dscp value',
        type=int)

    aparser.add_argument(
        '-L', '--flowlabel',
        help='set the IPv6 flow label',
        type=int)

    aparser.add_argument(
        '-Z', '--zerocopy',
        help='Use sendfile (not really zero copy, that is different)',
        action='store_true')

    aparser.add_argument(
        '-O', '--omit',
        help='perform pre-test for N seconds and omit the pre-test statistics',
        type=int)

    aparser.add_argument(
        '-T', '--title',
        help='prefix every output line with this string',
        type=str)

    aparser.add_argument(
        '--extra-data',
        help='extra data string to include in the client and server JSON',
        type=str)

    aparser.add_argument(
        '--get-server-output',
        help='get results from server',
        action='store_true')

    aparser.add_argument(
        '--udp-counters-64bit',
        help='use 64-bit counters in UDP test packets',
        action='store_true')

    aparser.add_argument(
        '--repeating-payload',
        help='use repeating pattern in payload instead of randomized payload (like iperf2)',
        action='store_true')

    aparser.add_argument(
        '--dont-fragment',
        help='set IPv4 Do not fragment flag',
        action='store_true')

    aparser.add_argument(
        '--username',
        help='username for authentication',
        type=str)

    aparser.add_argument(
        '--rsa-public-key-path',
        help='path to the RSA public key used to encrypt authentication credentials',
        type=str)

    args = vars(aparser.parse_args())

    for unsupported in UNSUPPORTED:
        if args.get(unsupported) is True:
            print("Option {} is not yet supported".format(unsupported))
            sys.exit(1)
        if (args.get(unsupported) is not None) and \
            (args.get(unsupported) is not False) and \
            (not args.get(unsupported) == 0):
            print("Option {} is not yet supported".format(unsupported))
            sys.exit(1)


    config = json.load(open(args.get("config")))
    params = json.load(open(args.get("params")))
    mappings = json.load(open("mappings.json", "r+"))

    for param, mapping in mappings.items():
        if args.get(param) is not None:
            try:
                for conf in mapping["c"]:
                    config[conf] = args[param]
            except TypeError:
                config[param] = args[param]
            except KeyError:
                pass

            try:
                for parm in mapping["p"]:
                    params[parm] = args[param]
            except TypeError:
                params[param] = args[param]
            except KeyError:
                pass

    if args.get("client") is not None and args.get("server"):
        print("You cannot select server and client mode at the same time")
        sys.exit(1)

    if args.get("udp"):
        params["udp"] = 1
        del params["tcp"]

    if args.get("client") is not None:
        config["target"] = args["client"]
        client = TestClient(config, params)
        return client.run()

    if args.get("server"):
        server = TestServer(config, params)
        return server.run()

    return 1

if __name__ == "__main__":
    main()
