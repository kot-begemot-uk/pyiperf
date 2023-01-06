#!/usr/bin/python3
'''Iperf external helper'''

import struct
import threading
from socketserver import TCPServer, UDPServer, BaseRequestHandler
from iperf_data import Counters, UDP_CONNECT_REPLY
from iperf_control import COOKIE_SIZE

class UDPRequestHandler(BaseRequestHandler):
    '''Handler for UDP Data'''

    def handle(self):

        #pylint: disable=unused-variable
        (addr, req) = self.request.recv(self.server.bufsize)

        try:
            if buf is not None:
                self.server.state[addr].process_header(buff)
                self.server.bytes_received = self.server.bytes_received + len(buff)
        except KeyError:
            self.server.state[addr] = Counters()
            self.request.sendto(struct.pack("i", UDP_CONNECT_REPLY), addr)


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
            self.bufsize = self.params["MSS"]
        except KeyError:
            self.bufsize = self.params["len"]

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
