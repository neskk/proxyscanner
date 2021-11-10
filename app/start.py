#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import sys
import time

from timeit import default_timer

from proxytools import utils
from proxytools.config import Config
from proxytools.proxy_tester import ProxyTester
from proxytools.proxy_parser import MixedParser, HTTPParser, SOCKSParser
from proxytools.models import init_database, Proxy, ProxyProtocol

log = logging.getLogger()


def check_configuration(args):
    if not args.proxy_file and not args.proxy_scrap:
        log.error('You must supply a proxylist file or enable scrapping.')
        sys.exit(1)

    if args.proxy_protocol == 'all':
        args.proxy_protocol = None
    elif args.proxy_protocol == 'http':
        args.proxy_protocol = ProxyProtocol.HTTP
    else:
        args.proxy_protocol = ProxyProtocol.SOCKS5

    if not args.proxy_judge:
        log.error('You must specify a URL for an AZenv proxy judge.')
        sys.exit(1)

    if args.tester_max_concurrency <= 0:
        log.error('Proxy tester max concurrency must be greater than zero.')
        sys.exit(1)

    args.local_ip = None
    if not args.tester_disable_anonymity:
        local_ip = utils.get_local_ip(args.proxy_judge)

        if not local_ip:
            log.error('Failed to identify local IP address.')
            sys.exit(1)

        log.info('External IP address found: %s', local_ip)
        args.local_ip = local_ip

    if args.proxy_refresh_interval < 15:
        log.warning('Checking proxy sources every %d minutes is inefficient.',
                    args.proxy_refresh_interval)
        args.proxy_refresh_interval = 15
        log.warning('Proxy refresh interval overriden to 15 minutes.')

    args.proxy_refresh_interval *= 60

    if args.proxy_scan_interval < 5:
        log.warning('Scanning proxies every %d minutes is inefficient.',
                    args.proxy_scan_interval)
        args.proxy_scan_interval = 5
        log.warning('Proxy scan interval overriden to 5 minutes.')

    args.proxy_scan_interval *= 60

    if args.output_interval < 15:
        log.warning('Outputting proxylist every %d minutes is inefficient.',
                    args.output_interval)
        args.output_interval = 15
        log.warning('Proxylist output interval overriden to 15 minutes.')

    args.output_interval *= 60

    disabled_values = ['none', 'false']
    if args.output_http.lower() in disabled_values:
        args.output_http = None
    if args.output_socks.lower() in disabled_values:
        args.output_socks = None
    if (args.output_kinancity and
            args.output_kinancity.lower() in disabled_values):
        args.output_kinancity = None
    if (args.output_proxychains and
            args.output_proxychains.lower() in disabled_values):
        args.output_proxychains = None
    if (args.output_rocketmap and
            args.output_rocketmap.lower() in disabled_values):
        args.output_rocketmap = None


def work(tester, parsers):
    # Validate proxy tester benchmark responses.
    if tester.validate_responses():
        log.info('Proxy tester response validation was successful.')
        # Launch proxy tester threads.
        tester.launch()
    else:
        log.critical('Proxy tester response validation failed.')
        sys.exit(1)

    # Fetch and insert new proxies from configured sources.
    for proxy_parser in parsers:
        proxy_parser.load_proxylist()

    # Remove failed proxies from database.
    Proxy.clean_failed()

    refresh_timer = default_timer()
    output_timer = default_timer()
    errors = 0
    while True:
        now = default_timer()
        if now > refresh_timer + args.proxy_refresh_interval:
            refresh_timer = now
            log.info('Refreshing proxylists configured from sources.')
            for proxy_parser in parsers:
                proxy_parser.load_proxylist()

            # Remove failed proxies from database.
            Proxy.clean_failed()

            # Validate proxy tester benchmark responses.
            if not tester.validate_responses():
                log.critical('Proxy tester response validation failed.')
                errors += 1
                if errors > 2:
                    sys.exit(1)

        if now > output_timer + args.output_interval:
            output_timer = now
            output(args)

        time.sleep(60)


def output(args):
    log.info('Outputting working proxylist.')

    working_http = []
    working_socks = []

    if args.output_kinancity:
        working_http = Proxy.get_valid(
            args.output_limit,
            args.tester_disable_anonymity,
            args.proxy_scan_interval,
            ProxyProtocol.HTTP)

        export_kinancity(args.output_kinancity, working_http)

    if args.output_proxychains:
        proxylist = Proxy.get_valid(
            args.output_limit,
            args.tester_disable_anonymity,
            args.proxy_scan_interval,
            args.proxy_protocol)

        export_proxychains(args.output_proxychains, proxylist)

    if args.output_rocketmap:
        working_socks = Proxy.get_valid(
            args.output_limit,
            args.tester_disable_anonymity,
            args.proxy_scan_interval,
            ProxyProtocol.SOCKS5)

        export(args.output_rocketmap, working_socks)

    if args.output_http:
        if not working_http:
            working_http = Proxy.get_valid(
                args.output_limit,
                args.tester_disable_anonymity,
                args.proxy_scan_interval,
                ProxyProtocol.HTTP)

        export(args.output_http, working_http, args.output_no_protocol)

    if args.output_socks:
        if not working_socks:
            working_socks = Proxy.get_valid(
                args.output_limit,
                args.tester_disable_anonymity,
                args.proxy_scan_interval,
                ProxyProtocol.SOCKS5)

        export(args.output_socks, working_socks, args.output_no_protocol)


def export(filename, proxylist, no_protocol=False):
    if not proxylist:
        log.warning('Found no valid proxies in database.')
        return

    log.info('Writing %d working proxies to: %s',
             len(proxylist), filename)

    proxylist = [Proxy.url_format(proxy, no_protocol)
                 for proxy in proxylist]

    utils.export_file(filename, proxylist)


def export_kinancity(filename, proxylist):
    if not proxylist:
        log.warning('Found no valid proxies in database.')
        return

    log.info('Writing %d working proxies to: %s',
             len(proxylist), filename)

    proxylist = [Proxy.url_format(proxy) for proxy in proxylist]

    proxylist = '[' + ','.join(proxylist) + ']'

    utils.export_file(filename, proxylist)


def export_proxychains(filename, proxylist):
    if not proxylist:
        log.warning('Found no valid proxies in database.')
        return

    log.info('Writing %d working proxies to: %s',
             len(proxylist), filename)

    proxylist = [Proxy.url_format_proxychains(proxy) for proxy in proxylist]

    utils.export_file(filename, proxylist)


def cleanup():
    """ Handle shutdown tasks """
    log.info('Shutting down...')


if __name__ == '__main__':
    args = Config.get_args()

    utils.configure_logging(args, log)
    check_configuration(args)
    init_database(
        args.db_name, args.db_host, args.db_port, args.db_user, args.db_pass)

    proxy_tester = ProxyTester(args)
    proxy_parsers = [MixedParser(args)]

    protocol = args.proxy_protocol
    if protocol is None or protocol == ProxyProtocol.HTTP:
        proxy_parsers.append(HTTPParser(args))

    if protocol is None or protocol == ProxyProtocol.SOCKS5:
        proxy_parsers.append(SOCKSParser(args))

    try:
        work(proxy_tester, proxy_parsers)
    except (KeyboardInterrupt, SystemExit):
        output(args)

        # Signal the Event to stop the threads
        proxy_tester.running.set()
        log.info('Waiting for proxy tester to shutdown...')
    #except Exception as e:
    #    log.exception(e)
    finally:
        cleanup()
        sys.exit()

