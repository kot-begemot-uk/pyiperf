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
import iperf_control
from iperf_data_server import UDPDataServer, TCPDataServer

IGNORE_IO_STATES = [iperf_control.EXCHANGE_RESULTS,
                    iperf_control.DISPLAY_RESULTS,
                    iperf_control.TEST_END]

class TestServer(iperf_control.TestClient):
    '''Iperf3 compatible test server'''

    def __init__(self, config, params):

        super().__init__(config, params)

        self.control_listener = None
        self.test_server = None
        self.schedule = [(iperf_control.PARAM_EXCHANGE, 0.1)]
        self.start_time = None
        self.server = True
        self.control_active = True

    def end_test(self):
        '''Cleanup Test'''
        super().end_test()
        if self.test_server is not None:
            self.test_server.shutdown()
            self.test_server.worker.join()
            self.test_server = None

    def collate_results(self):
        '''Collate Results'''

        super().collate_results()
        stream_id = 1
        for state_entry in self.test_server.state.values():
            entry = {"bytes": state_entry.bytes_received,
                    "retransmits": 0,
                    "jitter": state_entry.jitter,
                    "errors": state_entry.cnt_error,
                    "packets": state_entry.packet_count,
                    "start_time": 0,
                    "end_time":time.time() - self.start_time,
                    "id":stream_id}
            stream_id = stream_id + 1
            if stream_id == 2:
                stream_id = 3

            self.results["streams"].append(entry)

    def state_transition(self, new_state):
        '''Transition iperf state'''

        result = False
        peer_state = None

        # These two states are special - we ignore anything from the peer
        # while handling them
        if self.control_active:
            if not new_state in IGNORE_IO_STATES:
                try:
                    self.ctrl_sock.setblocking(False)
                    buff = self.ctrl_sock.recv(1)
                    if len(buff) > 0:
                        peer_state = struct.unpack(iperf_control.STATE, buff)[0]
                except BlockingIOError:
                    pass
                except OSError:
                    new_state = iperf_control.TEST_END
                    self.control_active = False

            try:
                self.ctrl_sock.setblocking(True)
                if peer_state is None and (not self.state == new_state):
                    self.ctrl_sock.send(struct.pack(iperf_control.STATE, new_state))
            except OSError:
                new_state = iperf_control.TEST_END
                self.control_active = False

            if peer_state is not None:
                new_state = peer_state

        self.state = new_state

        if new_state == iperf_control.PARAM_EXCHANGE:
            self.params = self.json_recv(self.ctrl_sock)
            if self.params is not None:
                self.amend_schedule()
                if self.params.get("udp"):
                    self.test_server = UDPDataServer(self.config, self.params)
                if self.params.get("tcp"):
                    self.test_server = TCPDataServer(self.config, self.params)
                self.test_server.start()
                result = True
            else:
                return False
        elif new_state == iperf_control.TEST_START:
            result = self.start_test()
        elif new_state == iperf_control.CREATE_STREAMS:
            result = True
        elif new_state == iperf_control.TEST_RUNNING:
            result = True
        elif new_state == iperf_control.EXCHANGE_RESULTS:
            self.exchange_results()
            result = True
        elif new_state == iperf_control.DISPLAY_RESULTS:
            self.display_results()
            result = True
        elif new_state == iperf_control.TEST_END:
            self.state_transition(iperf_control.EXCHANGE_RESULTS)
            self.state_transition(iperf_control.DISPLAY_RESULTS)
            self.end_test()
            result =  True
        elif new_state == iperf_control.SERVER_TERMINATE:
            self.state_transition(iperf_control.DISPLAY_RESULTS)
            self.state = iperf_control.IPERF_DONE
            result = True
        elif new_state == iperf_control.ACCESS_DENIED:
            result = False
        elif new_state == iperf_control.SERVER_ERROR:
            result =  True

        return result

    def amend_schedule(self):
        '''Create a test schedule'''
        self.schedule.extend([
            (iperf_control.CREATE_STREAMS, 0.1),
            (iperf_control.TEST_START, 0.1)
        ])
        dur = 0
        while dur < self.params["time"] + 2:
            self.schedule.append(
                (iperf_control.TEST_RUNNING, self.config["interval"])
            )
            dur = dur + self.config["interval"]
        self.schedule.append((iperf_control.IPERF_DONE, 0.1))

    def run(self):
        '''Run the server'''
        running = False
        try:
            self.control_listener = \
                socket.create_server((self.config["target"], self.config["config_port"]), reuse_port=True)
            #pylint: disable=unused-variable
            self.ctrl_sock, addr = self.control_listener.accept()
            running = True
            self.ctrl_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.control_listener.close()
            self.config["cookie"] = self.ctrl_sock.recv(iperf_control.COOKIE_SIZE)
            for (state, duration) in self.schedule:
                if self.state_transition(state):
                    time.sleep(duration)
                else:
                    self.end_test()
                    break
            self.end_test()
        except KeyboardInterrupt:
            if running:
                self.state_transition(iperf_control.TEST_END)
                return False
        return True
