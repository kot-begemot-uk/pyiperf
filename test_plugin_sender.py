#!/usr/bin/python3
'''Run pyiperf demo/test plugin. Doubles up as an example on how to embed
testing code without the control plane.
'''

# pyiperf, Copyright (c) 2023 RedHat Inc
# pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

# This source code is licensed under both the BSD-style license (found in the
# LICENSE file in the root directory of this source tree) and the GPLv2 (found
# in the COPYING file in the root directory of this source tree).
# You may select, at your option, one of the above-listed licenses.


from argparse import ArgumentParser
import socket
import time
from iperf_control import TestClient, TEST_START
from iperf_utils import json_recv, json_send

DEFAULT_LISTEN = "/tmp/iperf-plugin.0"

def main():
    '''Run iperf3 compatible tester code'''

    aparser = ArgumentParser(description=main.__doc__)
    aparser.add_argument(
        '--listen',
        help='config file in json format',
        type=str,
        default=DEFAULT_LISTEN)

    args = vars(aparser.parse_args())

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(args["listen"])
    sock.listen()
    control, addr = sock.accept()
    config = json_recv(control)
    config["cookie"] = bytes.fromhex(config["cookie"])
    config["plugin"] = None
    params = json_recv(control)
    client = TestClient(config, params)
    client.create_streams()
    control.recv(1)
    client.start_test()
    while len(control.recv(1)) < 1:
        pass
    client.collate_results()
    json_send(control, client.results)
    print("Done")
    control.close()

if __name__ == "__main__":
    main()
