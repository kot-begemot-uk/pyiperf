#!/usr/bin/python3
'''Iperf external helper'''

# pyiperf, Copyright (c) 2023 RedHat Inc
# pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

# This source code is licensed under both the BSD-style license (found in the
# LICENSE file in the root directory of this source tree) and the GPLv2 (found
# in the COPYING file in the root directory of this source tree).
# You may select, at your option, one of the above-listed licenses.

import socket
import time
import struct
from iperf_data import Client
from iperf_utils import json_recv, json_send
TEST_START = 1
TEST_END = 4
STATE = "b"

class PluginClient(Client):
    '''Iperf compatible sender/receiver'''


    def run_test(self):
        '''Run the actual test'''
        self.start_time = now = time.clock_gettime(time.CLOCK_MONOTONIC)
        self.sock.send(struct.pack(STATE, TEST_START))
        try:
            while now < self.start_time + self.params["time"]:
                data = json_recv(self.sock)
                if data is not None:
                    self.result.update(data)
                if data is None or self.done:
                    break
                time.sleep(0.1)
        except BrokenPipeError:
            pass

    def connect(self):
        '''Connect to the other side'''
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.config["plugin"])
        self.config["cookie"] = self.config["cookie"].hex()
        self.config["plugin"] = None
        json_send(self.sock, self.config)
        json_send(self.sock, self.params)

    def shutdown(self):
        '''Shut down the stream and wait for result'''
        self.sock.send(struct.pack(STATE, TEST_END))
        super().shutdown()
