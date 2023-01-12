#!/usr/bin/python3
'''Iperf external helper'''

# pyiperf, Copyright (c) 2023 RedHat Inc
# pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

# This source code is licensed under both the BSD-style license (found in the
# LICENSE file in the root directory of this source tree) and the GPLv2 (found
# in the COPYING file in the root directory of this source tree).
# You may select, at your option, one of the above-listed licenses.

import struct
import threading
from socketserver import TCPServer, UDPServer, BaseRequestHandler
from iperf_data import Counters, UDP_CONNECT_REPLY
from iperf_utils import COOKIE_SIZE

class UDPRequestHandler(BaseRequestHandler):
    '''Handler for UDP Data'''

    def handle(self):

        #pylint: disable=unused-variable
        buff = self.request[0]
        addr = "{}:{}".format(self.client_address[0], self.client_address[1])

        if buff is not None:
            if self.server.state.get(addr) is not None:
                self.server.state[addr].process_header(buff)
                self.server.bytes_received = self.server.bytes_received + len(buff)
            else:
                self.server.state[addr] = Counters()
                self.request[1].sendto(struct.pack("i", UDP_CONNECT_REPLY), self.client_address)


class UDPDataServer(UDPServer):
    '''Data channel server'''
    def __init__(self, config, params):
        self.config = config
        self.params = params
        self.worker_data = {}
        self.bytes_received = 0
        self.worker = None
        self.state = {}
        try:
            self.max_packet_size = self.params["MSS"]
        except KeyError:
            self.max_packet_size = self.params["len"]

        super().__init__((config["target"], config["data_port"]), UDPRequestHandler, True)

    def start(self):
        '''Run the Server side'''
        self.worker = threading.Thread(target=self.serve_forever, name="UDP")
        self.worker.start()



class TCPRequestHandler(BaseRequestHandler):
    '''Handler for UDP Data'''

    def handle(self):

        (buff, addr) = self.request.recvfrom(COOKIE_SIZE)

        if self.server.state.get(addr) is None:
            self.server.state[addr] = Counters()

        while True:
            try:
                buff = self.request.recv(self.server.bufsize)
                if buff is not None:
                    self.server.state[addr].bytes_received = \
                        self.server.state[addr].bytes_received + len(buff)
            except BlockingIOError:
                pass
            except ConnectionResetError:
                break


class TCPDataServer(TCPServer):
    '''Data channel server'''
    def __init__(self, config, params):
        self.config = config
        self.params = params
        self.worker_data = {}
        self.bytes_received = 0
        self.worker = None
        self.state = {}
        self.allow_reuse_address = True
        try:
            self.bufsize = self.params["MSS"]
        except KeyError:
            self.bufsize = self.params["len"]
        super().__init__((config["target"], config["data_port"]), TCPRequestHandler, True)

    def start(self):
        '''Run the Server side'''

        self.worker = threading.Thread(target=self.serve_forever, name="UDP")
        self.worker.start()
