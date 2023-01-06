#!/usr/bin/python3
'''Iperf external helper'''

import struct
import socket
import time
import iperf_control
from iperf_data_server import UDPDataServer, TCPDataServer


class TestServer(iperf_control.TestClient):
    '''Iperf3 compatible test client'''

    def __init__(self, config, params):

        super().__init__(config, params)

        self.control_listener = None
        self.test_server = None
        self.schedule = None

    def create_streams(self):
        '''Create Streams'''

        self.control_listener.close()

        if self.params.get("udp"):
            self.test_server = UDPDataServer(self.config, self.params)
        if self.params.get("tcp"):
            self.test_server = TCPDataServer(self.config, self.params)

        self.test_server.start()


    def state_transition(self, new_state):
        '''Transition iperf state'''

        self.state = new_state
        result = False

        if new_state == iperf_control.TEST_START:
            result = self.start_test()
        elif new_state == iperf_control.CREATE_STREAMS:
            result = self.create_streams()
        elif new_state == iperf_control.TEST_RUNNING:
            result = True
        elif new_state == iperf_control.EXCHANGE_RESULTS:
            result = self.exchange_results()
        elif new_state == iperf_control.DISPLAY_RESULTS:
            result = self.end_test()
        elif new_state == iperf_control.IPERF_DONE:
            result =  True
        elif new_state == iperf_control.SERVER_TERMINATE:
            self.state_transition(iperf_control.DISPLAY_RESULTS)
            self.state = iperf_control.IPERF_DONE
            result = True
        elif new_state == iperf_control.ACCESS_DENIED:
            result = False
        elif new_state == iperf_control.SERVER_ERROR:
            result =  True

        self.ctrl_sock.send(struct.pack(iperf_control.STATE, new_state))

        return result

    def create_schedule(self):
        '''Create a test schedule'''
        self.schedule = [
            (iperf_control.PARAM_EXCHANGE, 0.1),
            (iperf_control.CREATE_STREAMS, 0.1),
            (iperf_control.TEST_START, 0.1)
        ]
        dur = 0
        while dur < self.params["time"]:
            self.schedule.append(
                (iperf_control.TEST_RUNNING, self.params["interval"])
            )
            dur = dur + self.params["interval"]
        self.schedule.extend([
            (iperf_control.EXCHANGE_RESULTS, 0.1),
            (iperf_control.DISPLAY_RESULTS, 0.1),
            (iperf_control.IPERF_DONE, 0.1)
        ])

    def run(self):
        '''Run the server'''
        self.control_listener = \
            socket.create_server((self.config["target"], self.config["config_port"]), reuse_port=True)
        while True:
            self.ctrl_sock, addr = self.control_listener.accept()
            self.config["cookie"] = self.ctrl_sock.recv(iperf_control.COOKIE_SIZE)
            self.create_schedule()
            for (state, duration) in self.schedule:
                print("State {} timer {}".format(state, duration))
                self.state_transition(state)
                time.sleep(duration)
            self.end_test()
        return True
