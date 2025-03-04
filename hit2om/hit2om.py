#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert export data to open metrics for backfilling with promtool into prometheus
"""
__author__  = "Mark Butterworth"
__version__ = "0.1.0 20250103"
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
import argparse
import psutil
import time
from typing import Tuple, Optional, Union, TextIO
from pathlib import Path
from datetime import datetime
from socket import gethostname


DEBUG = 0
VERBOSE = 0
FORCE = False

METRIC_PREFIX='vdbench_'
# DATETIME_FORMAT = r'%m/%d/%Y %H:%M:%S.%f'
EXPORTER_PORT = 8113

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


def active_vdb_flatfile() -> Tuple[int, Union[Path, None]]:
    firstvdb = None
    for proc in psutil.process_iter():
        outputarg = 0
        try:
            for i, arg in enumerate(proc.cmdline()):
                if arg.endswith('vdbench.jar'):
                    firstvdb = proc
                if arg == '-o':  # found the output option
                    outputarg = i+1
            if firstvdb:
                break
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass   # Continue with next process

    if firstvdb:
        workdir = Path(firstvdb.cwd())
        if outputarg > 0 and outputarg < len(firstvdb.cmdline()):
            workdir = Path(firstvdb.cmdline()[outputarg])
            flatfile = workdir / 'flatfile.html'
            if flatfile.is_file and flatfile.exists() and flatfile.stat().st_size > 0:
                return firstvdb.pid, flatfile
        return firstvdb.pid, None
    return -1, None


def vdb_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    for arg in proc.cmdline():
        if arg.endswith('vdbench.jar'):
            return True
    return False


def follow(fd: TextIO , timeout: int=60, pid: int=0):
    '''generator function that yields new lines added to a file
    '''
    start = time.perf_counter()
    while True:
        line = fd.readline()
        if not line:
            if timeout and time.perf_counter() >= start+timeout:
                print(f'\nWARNING: {timeout}sec timeout following: {fd.name}')
                break
            if pid and not vdb_alive(pid):
                print(f'\nWARNING: Vdbench process no longer alive: {pid}')
                break
            time.sleep(0.25)
            continue
        yield line
        start = time.perf_counter()


def process_flatfile(pid: int, flatfile: str, labels: Optional[dict]=None):
    labels['run'] = ''
  
    # Rather than using the default REGISTRY, use our own:
    #    - Once destroyed will clear out prevous metrics.
    registry = CollectorRegistry()
    REGISTRY.register(registry)
    header = None
    with open(flatfile, 'r') as fd:
        for line in follow(fd, 60):
            line = line.strip()
            if 'tod' in line:
                header = line.split()
                break
        
        if not header:
            print(f'ERROR: Header not found in flatfile: {fd.name}')
            return

        header = [ x.lower().replace('/', '_').replace('%', '_pct') for x in header ]
        print('Header:', header)
        
        gauges = { METRIC_PREFIX + k: Gauge(METRIC_PREFIX + k , '', labels.keys(), registry=registry) 
                  for k in header[3:] }
        if DEBUG:
            print(gauges)

        # fd.seek(0, os.SEEK_END)   # Go to end so we get the latest Summary Info
        lastrun = ''
        for line in follow(fd, 15, pid):
            values = line.split()
            if values[3].startswith('avg'):
                continue
            # logtime = values[1][:10] + ' ' + values[0]
            # timestamp = datetime.strptime(logtime, DATETIME_FORMAT).timestamp()
            run = values[2]
            if run != lastrun:
                print(f'\n{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} Monitoring run: {run} ', end='')
                for k in gauges:
                    gauges[k].clear()
                lastrun = run
            labels['run'] = run
            for i, val in enumerate(values[3:]):
                metric = METRIC_PREFIX + header[i+3]
                # gauges[metric]._timestamp = timestamp
                if val == 'n/a':
                    val = '0'
                if DEBUG:
                    print(metric, labels, val)
                gauges[metric].labels(**labels).set(val)
            if not DEBUG:
                print('.', end='')
        # Once complete unregister to avoid "Duplicate Metrics" errors:
        REGISTRY.unregister(registry)


def vdb_proc_monitor():
    # Start the prometheus exporter web server:
    start_http_server(EXPORTER_PORT)
    toggle = True

    while True:
        if toggle:
            print('Monitoring for Vdbench process with active flatfile...')
            toggle = not toggle
        vdb_pid, vdb_flatfile = active_vdb_flatfile()
        if vdb_pid and vdb_flatfile:
            toggle = not toggle
            labels = { 'hostname': gethostname(), 'resultdir': vdb_flatfile.parent.name }
            print(f'Vdbench is active on PID: {vdb_pid} {labels}')
            process_flatfile(vdb_pid, vdb_flatfile, labels)
        time.sleep(0.25)

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

    rc=0
    REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
    REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
    REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)
    vdb_proc_monitor()
 
    return rc          


if __name__=='__main__':
    retcode = cli()
    exit(retcode)

