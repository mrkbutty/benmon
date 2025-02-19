#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor vdbench and post to Graphite timeseries database
"""
__author__  = "Mark Butterworth"
__version__ = "0.1.0 20250217"
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
import socket
import psutil
import os.path
import time
import pickle
import struct
from typing import Tuple, Optional, Union, TextIO
from pathlib import Path
from datetime import datetime

DEBUG = 0
VERBOSE = 0
FORCE = False

ROOTPATH='vdbench'
DATETIME_FORMAT = r'%m/%d/%Y-%H:%M:%S-%Z'
CARBON_SERVER = '127.0.0.1'
CARBON_PICKLE_PORT = 2004

###############################################################################


def get_root_path() -> str:
    return ROOTPATH + '.' + socket.gethostname()


def graphite_metric(pathname: str, value: any, timestamp: Union[datetime, str, None] = None) -> tuple[str, any, datetime]:
    return (pathname, (timestamp, value))


def find_vdb_outputdir() -> Tuple[int, Union[Path, None]]:
    firstvdb = None
    workdir = None
    for proc in psutil.process_iter():
        outputarg = 0
        for i, arg in enumerate(proc.cmdline()):
            if arg.endswith('vdbench.jar'):
                firstvdb = proc
            if arg == '-o':  # found the output option
                outputarg = i+1
        if firstvdb:
            break
    
    if firstvdb:
        workdir = Path(firstvdb.cwd())
        if outputarg > 0 and outputarg < len(proc.cmdline()):
            workdir = Path(proc.cmdline()[outputarg])
    return proc.pid, workdir


def follow(fd: TextIO , timeout: int=60):
    '''generator function that yields new lines in a file
    '''
    start = time.perf_counter()
    while True:
        line = fd.readline()
        if not line:
            if timeout and time.perf_counter() >= start+timeout:
                break
            time.sleep(0.1)
            continue
        yield line
        start = time.perf_counter()
    print(f'WARNING: Timeout following: {fd.name}')


def process_flatfile(result_dir: str, sock, pathroot: Optional[str]=None, tags: Optional[dict]=None):
    flatfile = Path(result_dir) / 'flatfile.html'

    if os.path.isfile(flatfile):
        print(f'Found: {flatfile}')

    if tags:
        tagstr = ';'.join([ f'{k}={v}' for k,v in tags.items() ])
    
    header = None
    with open(flatfile, 'r') as fd:
        for line in follow(fd, 15):
            line = line.strip()
            if 'tod' in line:
                header = line.split()
                header = [ x.lower().replace('/', '_') for x in header ]
                print('Header:', header)
                continue
            if header:
                values = line.split()
                timestamp = int(datetime.strptime(values[1], DATETIME_FORMAT).timestamp())
                metrics = []
                for i, col in enumerate(values[2:]):
                    pathname = pathroot + '.' + header[i+2] if pathroot else header[i+2]
                    # if tags: # For some reason tags are not working!
                    #     pathname += ';' + tagstr
                    col.replace('/', '')
                    metrics.append(graphite_metric(pathname, col, timestamp))
                print('.', end='')
                print(metrics)
                payload = pickle.dumps(metrics, protocol=2)
                size = struct.pack("!L", len(payload))
                sock.sendall(size)
                sock.sendall(payload)
                # The plaintext protocol:
                # for metric in metrics:
                #     print (metric)
                #     sock.sendall(f'{metric[0]} {metric[1][1]} {metric[1][0]}'.encode())


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
    vdb_pid, vdb_output = find_vdb_outputdir()
    if vdb_pid and vdb_output and Path(vdb_output).is_dir:
        sock = socket.socket()
        try:
            sock.connect( (CARBON_SERVER, CARBON_PICKLE_PORT) )
        except socket.error:
            raise SystemExit("Couldn't connect to %(server)s on port %(port)d, is carbon-cache.py running?" % { 'server':CARBON_SERVER, 'port':CARBON_PICKLE_PORT })

        tags = { 'resultdir': vdb_output.name.replace('_', '+').replace('.', '_') }
        tags = { 'greeting': 'Hello' }
        process_flatfile(vdb_output, sock, get_root_path(), tags)
    else:
        print('WARNING: Cannot find Vdbench process or output dir')
    
    return rc          


if __name__=='__main__':
    retcode = cli()
    exit(retcode)

