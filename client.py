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
from helper_control import TestClient

def main():

    '''Run the client'''

    aparser = ArgumentParser(description=main.__doc__)
    aparser.add_argument(
        '--config',
        help='config file in json format',
        type=str)

    aparser.add_argument(
        '--params',
        help='iperf3 params file in json format',
        type=str)

    args = vars(aparser.parse_args())

    config = json.load(open(args.get("config")))
    params = json.load(open(args.get("params")))
    
    client = TestClient(config, params)

    client.run()

    

if __name__ == "__main__":
    main()
