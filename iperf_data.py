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
import threading
import time
from iperf_utils import bandwidth

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

class Client():
    '''Iperf compatible sender/receiver'''
    def __init__(self, config, params, stream_id):
        self.config = config
        self.params = params
        try:
            self.buff = bytearray(self.params["MSS"])
        except KeyError:
            self.buff = bytearray(self.params["len"])

        self.length = len(self.buff)

        self.counters = Counters()
        self.worker = None
        self.done = False
        self.result = {"id":stream_id}
        self.total = 0
        self.sock = None
        self.start_time = 0
        self.lock = threading.Lock()
        try:
            self.limit = bandwidth(self.config["bitrate"])
        except KeyError:
            self.limit = 0

    # pylint: disable=unused-argument
    def send(self, now):
        '''Send a UDP frame with appropriate information for jitter/delay'''
        try:
            if ((not now == self.start_time) and \
               self.total/(now - self.start_time) <= self.limit or \
               self.limit == 0):
                self.total = self.total + self.sock.send(self.buff)
        except BlockingIOError:
            pass

    # pylint: disable=unused-argument
    def receive(self, now):
        '''Send a UDP frame with appropriate information for jitter/delay'''
        try:
            self.buff = self.sock.recv(self.length, socket.MSG_DONTWAIT)
            self.total = self.total + len(self.buff)
        except BlockingIOError:
            pass

    def shutdown(self):
        '''Shutdown the server'''
        self.done = True
        if self.worker is not None:
            self.worker.join()
        self.sock.close()

    def run_test(self):
        '''Run the actual test'''
        self.start_time = now = time.clock_gettime(time.CLOCK_MONOTONIC)
        self.lock.acquire()
        try:
            while now < self.start_time + self.params["time"]:
                if self.params.get("reverse") is None:
                    self.send(now)
                else:
                    self.receive(now)
                now = time.clock_gettime(time.CLOCK_MONOTONIC)
                if self.done:
                    break
        except ConnectionRefusedError:
            pass
        except ConnectionResetError:
            pass
        except BrokenPipeError:
            pass

        self.result.update({"bytes": self.total,
                        "retransmits": 0,
                        "jitter": self.counters.jitter,
                        "errors": self.counters.cnt_error,
                        "packets": self.counters.packet_count,
                        "start_time": 0,
                        "end_time":now - self.start_time})
        self.lock.release()

    def connect(self):
        '''Connect to the other side'''

        self.sock.connect((self.config["target"], self.config["data_port"]))

    def start(self):
        '''Run a sender'''
        self.worker = threading.Thread(target=self.run_test)
        self.worker.start()

class UDPClient(Client):
    '''UDP Specific Client'''

    def send(self, now):
        '''Send a UDP frame with appropriate information for jitter/delay'''
        self.counters.parsed.packet_count = self.counters.parsed.packet_count + 1
        self.counters.parsed.sec = int(abs(now))
        self.counters.parsed.usec = int((now - self.counters.parsed.sec) * 1E6)
        self.counters.parsed.pack_into(self.buff)
        super().send(now)

    def receive(self, now):
        '''RX a UDP frame with appropriate information for jitter/delay'''
        super().receive(now)
        if len(self.buff) > 0:
            self.counters.process_header(self.buff)

    def connect(self):
        '''Connect to the other side'''
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        super().connect()
        self.sock.send(UDP_CONNECT_MSG)
        if struct.unpack("i", self.sock.recv(4))[0] == 0x39383736:
            return True
        self.sock.setblocking(False)
        return False

class TCPClient(Client):
    '''UDP Specific Client'''

    def connect(self):
        '''Connect to the other side'''
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        super().connect()
        self.sock.send(self.config["cookie"])
        self.sock.setblocking(False)
        return True
