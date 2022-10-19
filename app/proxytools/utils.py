#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import random
import socket
import struct
import sys
import time

from timeit import default_timer as timer

log = logging.getLogger(__name__)


class LogFilter(logging.Filter):
    """ Log filter based on log levels """
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level


def configure_logging(log, verbosity=0, output_path='logs', output_name='-app'):
    date = time.strftime('%Y%m%d_%H%M')
    filename = os.path.join(output_path, '{}{}.log'.format(date, output_name))
    filelog = logging.FileHandler(filename)
    formatter = logging.Formatter(
        '%(asctime)s [%(threadName)18s][%(module)20s][%(levelname)8s] '
        '%(message)s')
    filelog.setFormatter(formatter)
    log.addHandler(filelog)

    # Redirect messages lower than WARNING to stdout
    stdout_hdlr = logging.StreamHandler(sys.stdout)
    stdout_hdlr.setFormatter(formatter)
    log_filter = LogFilter(logging.WARNING)
    stdout_hdlr.addFilter(log_filter)
    stdout_hdlr.setLevel(5)

    # Redirect messages equal or higher than WARNING to stderr
    stderr_hdlr = logging.StreamHandler(sys.stderr)
    stderr_hdlr.setFormatter(formatter)
    stderr_hdlr.setLevel(logging.WARNING)

    log.addHandler(stdout_hdlr)
    log.addHandler(stderr_hdlr)

    # Set logging verbosity level
    if not verbosity:
        log.setLevel(logging.INFO)
    elif verbosity > 0:
        log.setLevel(logging.DEBUG)
        arg_str = 'v' * verbosity
        log.info(f'Running in verbose mode (-{arg_str}).')

    if verbosity < 2:
        logging.getLogger('peewee').setLevel(logging.INFO)
    if verbosity < 3:
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.ERROR)


def load_file(filename):
    lines = []

    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()

            # Ignore blank lines and comment lines.
            if len(stripped) == 0 or line.startswith('#'):
                continue

            lines.append(lines)

        log.info('Read %d lines from file %s.', len(lines), filename)

    return lines


def export_file(filename, content):
    with open(filename, 'w', encoding='utf-8') as file:
        file.truncate()
        if isinstance(content, list):
            for line in content:
                file.write(line + '\n')
        else:
            file.write(content)


def validate_ip(ip):
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(part) < 256 for part in parts)
    except ValueError:
        # One of the "parts" is not convertible to integer.
        log.warning('Bad IP: %s', ip)
        return False
    except (AttributeError, TypeError):
        # Input is not even a string.
        log.warning('Weird IP: %s', ip)
        return False


def ip2int(addr):
    return struct.unpack('!I', socket.inet_aton(addr))[0]


def int2ip(addr):
    return socket.inet_ntoa(struct.pack('!I', addr))


def random_ip():
    return int2ip(random.randint(1, 0xffffffff))


def time_func(func):
    """ Wrapper function to measure the execution time of a function """
    def wrap_func(*args, **kwargs):
        t1 = timer()
        result = func(*args, **kwargs)
        t2 = timer()
        print(f'Function {func.__name__!r} executed in {(t2-t1):.3f}s')
        return result
    return wrap_func


def print_dicts(func):
    """ Wrapper function to print the dicts query """
    def wrap_func(*args, **kwargs):
        result = [m for m in func(*args, **kwargs).dicts()]
        return result
    return wrap_func