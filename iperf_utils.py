#!/usr/bin/python3
'''Iperf json utilities'''

# pyiperf, Copyright (c) 2023 RedHat Inc
# pyiperf, Copyright (c) 2023 Cambridge Greys Ltd

# This source code is licensed under both the BSD-style license (found in the
# LICENSE file in the root directory of this source tree) and the GPLv2 (found
# in the COPYING file in the root directory of this source tree).
# You may select, at your option, one of the above-listed licenses.

import json
import random
import struct
import re

RNDCHARS = "abcdefghijklmnopqrstuvwxyz234567"
COOKIE_SIZE = 37
JSONL = "!i"

BWIDTH_RE = re.compile(r"(\d+)([K,k,M,m,G,g])")

def bandwidth(arg):
    '''Translate bandwidth prefix'''
    ret = arg
    try:
        match = BWIDTH_RE.search(arg)
        if match is not None:
            ret = int(match.group(1))
            if match.group(2) == 'K':
                ret = 125 * int(match.group(1))
            if match.group(2) == 'M':
                ret =  125000 * int(match.group(1))
            if match.group(2) == 'G':
                ret = 125000000 * int(match.group(1))
            if match.group(2) == 'k':
                ret = 1000 * int(match.group(1))
            if match.group(2) == 'm':
                ret = 1000000 * int(match.group(1))
            if match.group(2) == 'g':
                ret = 1000000000 * int(match.group(1))
    except TypeError:
        pass
    return int(ret)


def json_send(sock, data):
    '''Send JSON data'''
    buff = json.dumps(data).encode("ascii", "ignore")
    try:
        if sock.send(struct.pack(JSONL, len(buff))) < 4 or sock.send(buff) < len(buff):
            return False
    except OSError:
        return False
    return True


def json_recv(sock):
    '''Receive JSON data'''
    try:
        buff = sock.recv(4)
        if len(buff) < 4:
            return None
        length = struct.unpack(JSONL, buff)[0]
        return json.loads(sock.recv(length))
    except OSError:
        pass
    return None

def make_cookie():
    '''Make a IPERF3 compatible "cookie"'''
    cookie = ""
    # pylint: disable=unused-variable
    for index in range(COOKIE_SIZE):
        cookie = cookie + RNDCHARS[random.randrange(0, len(RNDCHARS))]
    return cookie.encode("ascii")
