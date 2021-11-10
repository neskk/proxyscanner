#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import requests
import socket
import struct
import sys
import time

log = logging.getLogger(__name__)


class LogFilter(logging.Filter):
    """ Log filter based on log levels """
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level


def configure_logging(args, log):
    date = time.strftime('%Y%m%d_%H%M')
    filename = os.path.join(args.log_path, '{}-proxyscanner.log'.format(date))
    filelog = logging.FileHandler(filename)
    formatter = logging.Formatter(
        '%(asctime)s [%(threadName)18s][%(module)20s][%(levelname)8s] '
        '%(message)s')
    filelog.setFormatter(formatter)
    log.addHandler(filelog)

    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug('Running in verbose mode (-v).')
    else:
        log.setLevel(logging.INFO)

    logging.getLogger('peewee').setLevel(logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.ERROR)

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


def parse_azevn(response):
    lines = response.split('\n')
    result = {
        'remote_addr': None,
        'x_unity_version': None,
        'user_agent': None
    }
    try:
        for line in lines:
            if 'REMOTE_ADDR' in line:
                result['remote_addr'] = line.split(' = ')[1]
            if 'X_UNITY_VERSION' in line:
                result['x_unity_version'] = line.split(' = ')[1]
            if 'USER_AGENT' in line:
                result['user_agent'] = line.split(' = ')[1]
    except Exception as e:
        log.warning('Error parsing AZ Environment variables: %s', e)

    return result


def get_local_ip(proxy_judge):
    local_ip = None
    try:
        r = requests.get(proxy_judge)
        test = parse_azevn(r.text)
        local_ip = test['remote_addr']
    except Exception as e:
        log.exception('Failed to connect to proxy judge: %s', e)

    return local_ip


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
