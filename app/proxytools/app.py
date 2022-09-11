#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import sys
import time

from timeit import default_timer

from proxytools import utils
from proxytools.proxy_tester import ProxyTester
from proxytools.proxy_parser import MixedParser, HTTPParser, SOCKSParser
from proxytools.models import init_database, Proxy, ProxyTest, ProxyProtocol

log = logging.getLogger(__name__)


class App:

    def __init__(self, args):
        self.check_configuration(args)
        self.args = args
        init_database(args.db_name, args.db_host, args.db_port, args.db_user, args.db_pass)

        self.proxy_tester = ProxyTester(args)
        self.proxy_parsers = [MixedParser(args)]

        protocol = args.proxy_protocol
        if protocol is None or protocol == ProxyProtocol.HTTP:
            self.proxy_parsers.append(HTTPParser(args))

        if protocol is None or protocol == ProxyProtocol.SOCKS5:
            self.proxy_parsers.append(SOCKSParser(args))

        try:
            self.work()
        except (KeyboardInterrupt, SystemExit):
            self.output()

            # Signal the Event to stop the threads
            self.proxy_tester.running.set()
            log.info('Waiting for proxy tester to shutdown...')
        # except Exception as e:
        #     log.exception(e)
        finally:
            self.cleanup()
            sys.exit()

    def work(self):
        args = self.args
        tester = self.proxy_tester
        parsers = self.proxy_parsers

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
                self.output()

            time.sleep(60)

    def output(self):
        args = self.args
        log.info('Outputting working proxylist.')

        working_http = []
        working_socks = []

        if args.output_kinancity:
            working_http = Proxy.get_valid(
                args.output_limit,
                args.tester_disable_anonymity,
                args.proxy_scan_interval,
                ProxyProtocol.HTTP)

            self.export_kinancity(args.output_kinancity, working_http)

        if args.output_proxychains:
            proxylist = Proxy.get_valid(
                args.output_limit,
                args.tester_disable_anonymity,
                args.proxy_scan_interval,
                args.proxy_protocol)

            self.export_proxychains(args.output_proxychains, proxylist)

        if args.output_rocketmap:
            working_socks = Proxy.get_valid(
                args.output_limit,
                args.tester_disable_anonymity,
                args.proxy_scan_interval,
                ProxyProtocol.SOCKS5)

            self.export(args.output_rocketmap, working_socks)

        if args.output_http:
            if not working_http:
                working_http = Proxy.get_valid(
                    args.output_limit,
                    args.tester_disable_anonymity,
                    args.proxy_scan_interval,
                    ProxyProtocol.HTTP)

            self.export(args.output_http, working_http, args.output_no_protocol)

        if args.output_socks:
            if not working_socks:
                working_socks = Proxy.get_valid(
                    args.output_limit,
                    args.tester_disable_anonymity,
                    args.proxy_scan_interval,
                    ProxyProtocol.SOCKS5)

            self.export(args.output_socks, working_socks, args.output_no_protocol)

    def cleanup(self):
        """ Handle shutdown tasks """
        log.info('Shutting down...')

    def export(filename, proxylist, no_protocol=False):
        if not proxylist:
            log.warning('Found no valid proxies in database.')
            return

        log.info('Writing %d working proxies to: %s', len(proxylist), filename)

        proxylist = [Proxy.url_format(proxy, no_protocol) for proxy in proxylist]

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
