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
from proxytools.models import ProxyProtocol, Proxy
from proxytools.db import Database, DatabaseQueue

log = logging.getLogger(__name__)


class App:

    def __init__(self):
        self.args = Config.get_args()
        log.info(f'Found local IP: {self.args.local_ip}')
        self.db = Database()
        self.db_queue = DatabaseQueue.get_db_queue()
        self.manager = TestManager()
        self.parser = ProxyParser()

    def start(self):
        try:
            self.__launch()
            self.__work()
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception as e:
            log.exception(e)
        finally:
            self.__stop()
            self.__output()
            self.__cleanup()

        sys.exit(0)

    def __launch(self):
        # Validate proxy tester benchmark responses
        if self.manager.validate_responses():
            log.info('Test manager response validation was successful.')
            # Start database queue threads
            self.db_queue.start()
            # Launch proxy tester threads
            self.manager.start()
        else:
            log.error('Test manager response validation failed.')
            sys.exit(1)

        # Fetch and insert new proxies from configured sources
        self.parser.load_proxylist()

        # Handle SIGTERM gracefully
        signal.signal(signal.SIGTERM, utils.sigterm_handler)

    def __stop(self):
        log.info('Shutting down...')
        # Stop proxy tester threads
        self.manager.stop()
        # Stop database queue threads
        self.db_queue.stop()

    def __work(self):
        refresh_timer = default_timer()
        output_timer = default_timer()
        errors = 0

        while True:
            if self.manager.interrupt.is_set():
                break
            now = default_timer()

            self.db.print_stats()
            self.db_queue.print_stats()

            if now > refresh_timer + self.args.proxy_refresh_interval:
                refresh_timer = now
                log.info('Refreshing proxylists from configured sources.')
                self.parser.load_proxylist()

                # Validate proxy tester benchmark responses
                if not self.manager.validate_responses():
                    log.error('Proxy tester response validation failed.')
                    errors += 1
                    if errors > 2:
                        break
                else:
                    errors = 0

            # Regular proxylist output
            if now > output_timer + self.args.output_interval:
                output_timer = now
                self.__output()

            time.sleep(60)

    def __output(self):
        args = self.args
        log.info('Outputting working proxylist.')
        Proxy.database().connect()
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

        Proxy.database().close()

    def __cleanup(self):
        """ Handle shutdown tasks """
        Proxy.database().close()

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
