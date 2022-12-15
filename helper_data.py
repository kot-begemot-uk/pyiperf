#!/usr/bin/python3
'''Iperf external helper'''

from socketserver import UDPServer, BaseRequestHandler
import struct
import socket
import threading
import time

FORMAT32 = "!iii"
FORMAT64 = "!iil"
# this for some reason is in host order
UDP_CONNECT_MSG = struct.pack("i", 0x36373839)
UDP_CONNECT_REPLY = 0x39383736

class Header():
    '''Packet Header'''
    def __init__(self, buff=None, long_counters=False):

        if buff is None:
            self.sec = self.usec = self.packet_count = 0
        else:
            if long_counters:
                (self.sec, self.usec, self.packet_count) = struct.unpack(FORMAT64, buff)
            else:
                (self.sec, self.usec, self.packet_count) = struct.unpack(FORMAT32, buff)
        self.long_counters = long_counters

    def parse(self, buff):
        '''Pack the header for xmit'''
        if self.long_counters:
            (self.sec, self.usec, self.packet_count) = struct.unpack(FORMAT64, buff)
        else:
            (self.sec, self.usec, self.packet_count) = struct.unpack(FORMAT32, buff)

    def pack(self):
        '''Pack the header for xmit'''
        if self.long_counters:
            return struct.pack(FORMAT64, self.sec, self.usec, self.packet_count)
        return struct.pack(FORMAT32, self.sec, self.usec, self.packet_count)

    def pack_into(self, buff):
        '''Pack the header into a buffer for xmit'''
        if self.long_counters:
            struct.pack_into(FORMAT64, buff, 0, self.sec, self.usec, self.packet_count)
        struct.pack_into(FORMAT32, buff, 0, self.sec, self.usec, self.packet_count)

class Counters():
    '''Packet Counters'''
    def __init__(self):
        self.packet_count = 0
        self.peer_packet_count = 0
        self.jitter = 0.0
        self.prev_transit = 0.0
        self.outoforder_packets = 0
        self.cnt_error = 0
        self.bytes_received = 0

        self.first_packet = True
        self.parsed = Header()

    def process_header(self, buff):
        '''Process an incoming packet header'''

        self.parsed.parse(buff[:12])
        self.bytes_received = self.bytes_received + len(buff)

        if self.parsed.packet_count > self.packet_count:
            # seq going forward
            if self.parsed.packet_count > self.packet_count + 1:
                self.cnt_error = self.cnt_error + (self.parsed.packet_count -1) - self.packet_count

            self.packet_count = self.parsed.packet_count

        else:
            self.outoforder_packets = self.outoforder_packets + 1
            if self.cnt_error > 0:
                self.cnt_error = self.cnt_error - 1
        transit = time.clock_gettime(time.CLOCK_MONOTONIC) - self.parsed.sec - self.parsed.usec / 1E6

        if self.first_packet:
            self.prev_transit = transit
            self.first_packet = False

        diff = abs(transit - self.prev_transit)
        self.prev_transit = transit
        self.jitter = self.jitter + (diff - self.jitter)/16.0

class DataRequestHandler(BaseRequestHandler):
    '''Handler for UDP Data'''

    def handle(self):

        (addr, req) = self.request


        buff = req.recv(self.server.bufsize)
        if buff is not None:
            length = len(buff)
            if length > 0:
                self.server.bytes_received = self.server.bytes_received + length
            try:
                counters = self.server.worker_data[threading.current_thread().getName()]
            except KeyError:
                counters = Counters()
                self.server.worker_data[threading.current_thread().getName()] = counters
            counters.process_header(buff)


class DataServer(UDPServer):
    '''Data channel server'''
    def __init__(self, data, bufsize):
        self.bufsize = bufsize
        self.worker_data = {}
        self.bytes_received = 0
        self.worker = None
        super().__init__(data, DataRequestHandler, True)

    def start(self):
        '''Run the Server side'''
        self.worker = threading.Thread(target=self.serve_forever, name="UDP", daemon=1)
        self.worker.start()


class UDPSender():
    '''Iperf compatible sender'''
    def __init__(self, target, stream_id, params):
        self.target = target
        self.params = params
        self.buff = bytearray(self.params["MSS"])
        self.header = Header()
        self.worker = None
        self.done = False
        self.result = {"id":stream_id}

    def send(self, now):
        '''Send a UDP frame with appropriate information for jitter/delay'''
        self.header.packet_count = self.header.packet_count + 1
        self.header.sec = int(abs(now))
        self.header.usec = int((now - self.header.sec) * 1E6)
        self.header.pack_into(self.buff)
        self.sock.send(self.buff)

    def shutdown(self):
        '''Shutdown the server'''
        self.done = True
        if self.worker is not None:
            self.worker.join()

    def run_test(self):
        '''Run the actual test'''
        start = now = time.clock_gettime(time.CLOCK_MONOTONIC)
        try:
            while now < start + self.params["time"]:
                self.send(now)
                now = time.clock_gettime(time.CLOCK_MONOTONIC)
                if self.done: # reading/storing a single var in python is atomic
                    break
        except ConnectionRefusedError:
            pass
    
        self.result.update({"bytes": self.params["MSS"] * self.header.packet_count,
                        "retransmits": 0,
                        "jitter": 0.0,
                        "errors":0,
                        "packets": self.header.packet_count,
                        "start_time": 0,
                        "end_time":now - start})

    def connect(self):
        '''Connect to the other side'''

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect(self.target)
        self.sock.send(UDP_CONNECT_MSG)
        if (struct.unpack("i", self.sock.recv(4))[0] == 0x39383736):
            return True
        return False

    def start(self):
        '''Run a sender'''
        self.worker = threading.Thread(target=self.run_test, daemon=1)
        self.worker.start()
