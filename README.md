# pyiperf
Python implementation of iperf3

A set of modules and a simple commmand line utility which replicate the functionality of iperf3 in pure python. The performance is ~ 80% of the C implementation. This will be boosted to the same level as the pure C by using plugins in future versions.

The code is intended to be reusable and allow for direct embedding into test scripts and harnesses written in python.

Future versions will add plugins for direct access to CNDP, AF XDP and other backend dataplanes. I had the initial intention to add that to iperf3 proper. After fighting with its implied state being spread all over the place for 

Modules behaviour is controlled by two configuration objects - config and params. Config contains the local configuration which is not shared by server and client. Params is what ends up being sent to the server as a part of test parameter negotiation. The executable replicates most of the iperf executable functionality to override the defaults.

BUG report and contributions - via standard github means. Open an issue or create a pull request.
