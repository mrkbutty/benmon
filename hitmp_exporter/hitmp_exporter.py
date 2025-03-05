#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Hitachi RAID Manager "raidcfg" to gather elapsed and processing used counters
"""
__author__  = "Mark Butterworth"
__version__ = "0.1.0 20250304"
__license__ = "MIT"

# Ver 0.1.0 20250217  Initial version

# MIT License

# Copyright (c) 2023 Mark Butterworth

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import os
import argparse
import psutil
import time
import signal
import subprocess

from typing import Tuple, Optional, Union, TextIO, Dict
from pathlib import Path
from datetime import datetime
from socket import gethostname
from shutil import which

import prometheus_client
from prometheus_client import REGISTRY, start_http_server, CollectorRegistry, Gauge

DEBUG = 0
VERBOSE = 0
FORCE = False

METRIC_PREFIX='hitmp_'
# DATETIME_FORMAT = r'%m/%d/%Y %H:%M:%S.%f'
EXPORTER_PORT = 8213
HITMP_RMLOCATION = '/HORCM'
RAIDCFG = ''
RAIDCOM = ''

HEADER_MATCH = 'MP#'
HEADER_TRANSLATE = {
    'MP#': 'MPid',
    'E-Time(us)': 'Elapsed_Time',
    'B-Time(us)': 'Busy_Time',
    'OT(us)': 'Open_Target_Time',
    'OI(us)': 'Open_Initiator_Time',
    'OE(us)': 'Open_Externmal_Time',
    'MT(us)': 'Mainframe_Target_Time',
    'ME(us)': 'Mainframe_External_Time',
    'BE(us)': 'Backend_Time',
    'Sys(us)': 'System_Time',
}


###############################################################################


# class TimestampedGauge(Gauge):
#     def __init__(self, *args, timestamp=None, **kwargs):
#         self._timestamp = timestamp
#         super().__init__(*args, **kwargs)

#     def collect(self):
#         metrics = super().collect()
#         for metric in metrics:
#             metric.samples = [ 
#                 type(sample)(sample.name, sample.labels, sample.value, self._timestamp, sample.exemplar)
#                 for sample in metric.samples
#             ]
#         return metrics



def sigterm_handler(signo, stack_frame):
    print(f'{signal.strsignal(signo)} received, Exiting...')
    # Raises SystemExit(0):
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)


def get_serialno_power() -> Tuple[str, str]:
    cmd = f'{RAIDCOM} get system'.split()
    if DEBUG:
        print(f'cmd: {cmd}')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if DEBUG:
        print('stdout:', result.stdout)
        print('stderr:', result.stderr)
    for line in result.stdout.split('\n'):
        if line.startswith('Serial'):
            serialno = line.split()[-1]
        if line.startswith('AVE(W)'):
            watts = line.split()[-1]
            break
    return (serialno, watts)


def mpstat_monitor(mpulookup: Dict, interval: int) -> int:
    hostname = os.environ.get('HITMP_EXPORTER_HOSTNAME', gethostname())

    registry = CollectorRegistry()
    REGISTRY.register(registry)

    # gauges = dict()
    # for key in HEADER_TRANSLATE:
    #     gauges[key] = Gauge(METRIC_PREFIX + HEADER_TRANSLATE[key][0] , HEADER_TRANSLATE[key][1], labels.keys(), registry=registry) 
    power_labels = { 'hostname': hostname, 'serialno': '????????', 'MPid': '???', 'MPU': '?????' }
    power_gauge = Gauge(METRIC_PREFIX + 'power_watts', 'Storage Power usage (Watts)', power_labels.keys(), registry=registry)
    elapsed_labels = { 'hostname': hostname, 'serialno': '????????', 'MPid': '???', 'MPU': '?????' }
    elapsed_gauge = Gauge(METRIC_PREFIX + 'elapsed_total', 'Total elapsed time during the measurement (us)', elapsed_labels.keys(), registry=registry)
    coretime_labels = { 'hostname': hostname, 'serialno': '????????', 'MPid': '000', 'MPU': '?????', 'mode': 'unknown' }
    coretime_gauge = Gauge(METRIC_PREFIX + 'coretime_total', 'Core busy time over the elapsed period labeled by mode (us)', coretime_labels.keys(), registry=registry)

    # Gauge will scrape:
    # raidcfg -a qry -o stat -pmp 0 8
    # MP#   E-Time(us) B-Time(us)     OT(us)     OI(us)     OE(us)     MT(us)     ME(us)     BE(us)    Sys(us)
    #   0   0x9aae6529 0xc1bd71d5 0xfcc8f3ab 0x00000000 0x00000000 0x00000000 0x00000000 0xae65ec34 0x168e91f6
    #   1   0x9aa0c118 0x59190a80 0x55903954 0x00000000 0x00000000 0x00000000 0x00000000 0x9fa07938 0x63e857f4
    #   2   0x9d10238a 0x0628bc93 0x4a0eb055 0x00000000 0x00000000 0x00000000 0x00000000 0x754d0c56 0x46ccffe8
    #   3   0x9c24613b 0xdfb37f60 0xd9ebe538 0x00000000 0x00000000 0x00000000 0x00000000 0x6673303f 0x9f5469e9
    #   4   0x98e3cb61 0x9d2b4afc 0xb5ce4a6d 0x00000000 0x00000000 0x00000000 0x00000000 0x6eca9bca 0x789264c5
    #   5   0x97ef7c31 0xc8d8af15 0x5da53884 0x00000000 0x00000000 0x00000000 0x00000000 0x38e22b7e 0x32514b13
    #   6   0x9aaf6fe4 0x4873beea 0xe7ca316d 0x00000000 0x00000000 0x00000000 0x00000000 0x7eac129f 0xe1fd7ade
    #   7   0x99df5a0e 0xd8aca4d3 0x7a7565f9 0x00000000 0x00000000 0x00000000 0x00000000 0x44e10243 0x19563c97

    while True:
        start_timer = time.perf_counter()

        serialno, watts = get_serialno_power()
        power_labels['serialno'] = serialno
        power_gauge.labels(**power_labels).set(watts)

        for mpbank in range(16):
            cmd = f'{RAIDCFG} -a qry -o stat -pmp {mpbank} 8'.split()
            if DEBUG:
                print(f'cmd: {cmd}')
            result = subprocess.run(cmd, capture_output=True, text=True)
            if DEBUG > 1:
                print('stdout:\n', result.stdout)
                print('stderr:\n', result.stderr)

            for line in result.stdout.split('\n'):
                if line.startswith(HEADER_MATCH):
                    headers = line.split()
                elif line:
                    cols = line.split()
                    if cols[1] == '0x00000000':
                        continue   # Skip if no elasped time, i.e. MP core does not exist

                    if mpulookup:
                        mpnum = int(cols[0])
                        for i in mpulookup:
                            if mpnum >= i:
                                mpuname = mpulookup[i]
                        elapsed_labels['MPU'] = mpuname
                        coretime_labels['MPU'] = mpuname
                    mpid = f'{int(cols[0]):03d}'
                    elapsed_labels['MPid'] = mpid
                    coretime_labels['MPid'] = mpid

                    elapsed = float(int(cols[1], 16))
                    if DEBUG > 2:
                        print('ELAPSED:', elapsed_labels, elapsed)
                    elapsed_gauge.labels(**elapsed_labels).set(elapsed)
                    for i, header in enumerate(headers):
                        if i < 2 or cols[i] == '0x00000000':
                            continue
                        coretime = float(int(cols[i], 16))
                        coretime_labels['mode'] = HEADER_TRANSLATE[header]
                        if DEBUG > 2:
                            print('CORETIME:', header, coretime_labels, coretime)
                        coretime_gauge.labels(**coretime_labels).set(coretime)
            print('.', end='')
        duration = time.perf_counter() - start_timer
        if DEBUG:
            print('Loop Execution time (secs):', duration )
        time.sleep(max(0, interval-duration))

    REGISTRY.unregister(registry)


def check_raid_manager(rmdir: str):
    global RAIDCFG, RAIDCOM

    RAIDCFG = Path(rmdir) / 'usr/bin/raidcfg'
    RAIDCOM = Path(rmdir) / 'usr/bin/raidcom'

    if not RAIDCFG.is_file() or not os.access(RAIDCFG, os.X_OK) or \
        not RAIDCOM.is_file() or not os.access(RAIDCOM, os.X_OK):
        print('WARNING: Cannot find raidcfg or raidcom executables')
    # TODO: Check HORCM operation is working.


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.version = __version__
    parser.add_argument('-V', '--version', action='version')
    parser.add_argument('-D', '--debug', action='count',
        help='Increase debug level, e.g. -DDD = level 3.')
    parser.add_argument('-v', '--verbose', action='count',
        help='Increase verbose level, e.g. -vv = level 2.')
    parser.add_argument('-f', '--force', action='store_true',
         help='Force')
    parser.add_argument('-r', '--rmdir', type=str, default=HITMP_RMLOCATION,
         help='RAID Manager directory location ')
    parser.add_argument('-i', '--interval', type=int, default=15,
         help='Intervals between collection')
    parser.add_argument('MPUnames', type=str, nargs='*',
         help='Provide MPU to core mappings: <Name>:<starting-MP#> <Name>:<starting-MP#> ... (enables MPU labeling)')
    

    args = parser.parse_args()
    global DEBUG, VERBOSE, FORCE
    if args.debug:
        DEBUG = args.debug
        print('Python version:', sys.version)
        print('DEBUG LEVEL:', args.debug)
        print('Arguments:', args)

    if sys.version_info < (3, 9):
        print('ERROR: Minimum required python version is 3.9')
        return 10

    VERBOSE = args.verbose



    mpudict = {}
    for mpname in args.MPUnames:
        name, mpid = mpname.split(':',1)
        if not name or not mpid or not mpid.isdigit():
            print(f'ERROR: Invalid MPU naming: {mpname}')
            return 20
        mpudict[int(mpid)] = name

    if not mpudict:
        print('WARNING: You have not supplied MPU name mappings: MPU labels will not be populated.')

    rc=0

    # Disable default python metrics:
    REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
    REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
    REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

    rmdir = os.environ.get('HITMP_RMLOCATION', args.rmdir)
    check_raid_manager(rmdir)
    start_http_server(EXPORTER_PORT)
    rc = mpstat_monitor(mpudict, args.interval)
    return rc          


if __name__=='__main__':
    retcode = cli()
    exit(retcode)

