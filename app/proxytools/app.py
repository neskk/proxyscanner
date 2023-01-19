#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import signal
import sys
import time

from timeit import default_timer

from proxytools import utils
from proxytools.config import Config
from proxytools.test_manager import TestManager
from proxytools.proxy_parser import ProxyParser
from proxytools.models import init_database, ProxyProtocol, Proxy

log = logging.getLogger(__name__)


class App:

    def __init__(self):
        args = Config.get_args()

        init_database(
            args.db_name,
            args.db_host,
            args.db_port,
            args.db_user,
            args.db_pass)

        self.args = args
        self.manager = TestManager()
        self.parser = ProxyParser()

    def start(self):
        try:
            self.__launch()
            self.__work()
        except (KeyboardInterrupt, SystemExit):
            self.__output()

            # Signal manager to stop threads
            log.info('Waiting for proxy tests to finish...')
            self.manager.stop()
        except Exception as e:
            log.exception(e)
        finally:
            self.__cleanup()
            sys.exit()

    def __launch(self):
        # Validate proxy tester benchmark responses.
        if self.manager.validate_responses():
            log.info('Test manager response validation was successful.')
            # Launch proxy tester threads.
            self.manager.start()
        else:
            log.critical('Test manager response validation failed.')
            sys.exit(1)

        # Unlock proxies stuck in testing.
        query = Proxy.unlock_stuck()
        rows = query.execute()
        log.info('Unlocked %d proxies stuck in testing.', rows)

        # Fetch and insert new proxies from configured sources.
        self.parser.load_proxylist()

        # Handle SIGTERM gracefully
        signal.signal(signal.SIGTERM, utils.sigterm_handler)

    def __work(self):
        refresh_timer = default_timer()
        output_timer = default_timer()
        errors = 0

        while True:
            if self.manager.interrupt.is_set():
                sys.exit(1)

            now = default_timer()
            if now > refresh_timer + self.args.proxy_refresh_interval:
                refresh_timer = now
                log.info('Refreshing proxylists from configured sources.')
                self.parser.load_proxylist()
                # Unlock proxies stuck in testing.
                query = Proxy.unlock_stuck()
                rows = query.execute()
                log.info('Unlocked %d proxies stuck in testing.', rows)

                # Remove failed proxies from database.
                query = Proxy.delete_failed()

                # Validate proxy tester benchmark responses.
                if not self.manager.validate_responses():
                    log.critical('Proxy tester response validation failed.')
                    errors += 1
                    if errors > 2:
                        sys.exit(1)

            if now > output_timer + self.args.output_interval:
                output_timer = now
                self.__output()

            time.sleep(60)

    def __output(self):
        args = self.args
        log.info('Outputting working proxylist.')

        working_http = []
        working_socks = []

        if args.output_kinancity:
            query = Proxy.get_valid(
                args.output_limit,
                args.proxy_scan_interval,
                ProxyProtocol.HTTP)
            working_http = query.execute()

            App.export_kinancity(args.output_kinancity, working_http)

        if args.output_proxychains:
            query = Proxy.get_valid(
                args.output_limit,
                args.proxy_scan_interval,
                args.proxy_protocol)
            proxylist = query.execute()

            App.export_proxychains(args.output_proxychains, proxylist)

        if args.output_rocketmap:
            query = Proxy.get_valid(
                args.output_limit,
                args.proxy_scan_interval,
                ProxyProtocol.SOCKS5)
            working_socks = query.execute()

            App.export(args.output_rocketmap, working_socks)

        if args.output_http:
            if not working_http:
                query = Proxy.get_valid(
                    args.output_limit,
                    args.proxy_scan_interval,
                    ProxyProtocol.HTTP)
                working_http = query.execute()

            App.export(args.output_http, working_http, args.output_no_protocol)

        if args.output_socks:
            if not working_socks:
                query = Proxy.get_valid(
                    args.output_limit,
                    args.proxy_scan_interval,
                    ProxyProtocol.SOCKS5)
                working_socks = query.execute()

            App.export(args.output_socks, working_socks, args.output_no_protocol)

    def __cleanup(self):
        """ Handle shutdown tasks """
        log.info('Shutting down...')

    def export(filename, proxylist, no_protocol=False):
        if not proxylist:
            log.warning('Found no valid proxies in database.')
            return

        log.info('Writing %d working proxies to: %s', len(proxylist), filename)

        proxylist = [proxy.url(no_protocol) for proxy in proxylist]

        utils.export_file(filename, proxylist)

    def export_kinancity(filename, proxylist):
        if not proxylist:
            log.warning('Found no valid proxies in database.')
            return

        log.info('Writing %d working proxies to: %s',
                 len(proxylist), filename)

        proxylist = [proxy.url() for proxy in proxylist]

        proxylist = '[' + ','.join(proxylist) + ']'

        utils.export_file(filename, proxylist)

    def export_proxychains(filename, proxylist):
        if not proxylist:
            log.warning('Found no valid proxies in database.')
            return

        log.info('Writing %d working proxies to: %s',
                 len(proxylist), filename)

        proxylist = [proxy.url_proxychains() for proxy in proxylist]

        utils.export_file(filename, proxylist)
