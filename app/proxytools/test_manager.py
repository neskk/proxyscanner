#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
import queue
import time

from timeit import default_timer
from threading import Event, Lock, Thread

from requests.packages import urllib3

from .ip2location import IP2LocationDatabase
from .config import Config
from .models import Proxy, get_connection_stats
from .proxy_tester import ProxyTester
from .testers.azenv import AZenv
from .testers.google import Google
from .testers.pogo_signup import PoGoSignup
from .testers.pogo_login import PoGoLogin
from .testers.pogo_api import PoGoAPI


log = logging.getLogger(__name__)


class TestManager():
    """
    Manage proxy tester threads and overall progress.
    """

    def __init__(self):
        self.args = Config.get_args()
        self.interrupt = Event()
        self.stats_lock = Lock()
        self.ip2location = IP2LocationDatabase(self.args)

        self.total_success = 0
        self.total_fail = 0
        self.notice_success = 0
        self.notice_fail = 0

        # Making unverified HTTPS requests prints warning messages
        # https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
        urllib3.disable_warnings()
        # logging.captureWarnings(True)

        self.local_ip = self.find_local_ip()
        self.plan_test_cycle()

        # Initialize queue of proxies to test
        self.queue = queue.Queue(maxsize=self.args.manager_testers * 2)

    def find_local_ip(self):
        ip = None
        try:
            r = requests.get(self.args.proxy_judge)
            r.raise_for_status()
            response = r.text
            lines = response.split('\n')

            for line in lines:
                if 'REMOTE_ADDR' in line:
                    ip = line.split('=')[1].strip()
                    break

            log.info('Local IP: %s', ip)
        except Exception as e:
            log.exception('Failed to connect to proxy judge: %s', e)

        return ip

    def plan_test_cycle(self):
        # Test sequence to be executed on each proxy
        self.test_classes = [Google]

        if self.args.test_pogo:
            self.test_classes.insert(1, PoGoSignup)
            self.test_classes.insert(1, PoGoLogin)
            self.test_classes.insert(1, PoGoAPI)
        if self.args.test_anonymity:
            self.test_classes.insert(1, AZenv)

    def validate_responses(self):
        log.info('Validating proxy test suites.')
        for test_class in self.test_classes:
            test = test_class(self)
            if not test.validate():
                log.error('Invalid response from test: %s')
                return False

        return True

    def validate_ipify(self):
        try:
            r = requests.get('https://api.ipify.org/?format=json')
            r.raise_for_status()
            response = r.json()

            ip = response['ip']
            if ip == self.local_ip:
                return True

            log.error('Local IP (%s) does not match response (%s)', self.local_ip, ip)
        except Exception as e:
            log.exception('Failed to connect to API: %s', e)
        return False

    def mark_success(self):
        with self.stats_lock:
            self.total_success += 1
            self.notice_success += 1

    def mark_fail(self):
        with self.stats_lock:
            self.total_fail += 1
            self.notice_fail += 1

    def reset_notice_stats(self):
        with self.stats_lock:
            self.notice_success = 0
            self.notice_fail = 0

    def fill_queue(self):
        num = self.queue.maxsize - self.queue.qsize()
        protocol = self.args.proxy_protocol

        try:
            query = Proxy.need_scan(limit=num, protocols=protocol)

            for proxy in query:
                if self.lock_proxy(proxy):
                    self.queue.put(proxy)

        except Exception as e:
            log.warning(f'Failed to refresh proxy testing queue: {e}')
            return False

        return True

    def release_queue(self):
        while not self.queue.empty():
            proxy = self.queue.get(block=False)
            proxy.unlock()

    def lock_proxy(self, proxy):
        row_count = proxy.lock_for_testing()
        if row_count != 1:
            log.warning(f'Failed to lock proxy #{proxy.id} for testing.')
            return False

        return True

    def get_proxy(self):
        try:
            proxy = self.queue.get(timeout=1)
            return proxy
        except queue.Empty:
            return None

    def start(self):
        # Start test manager thread
        self.manager = Thread(
            name='test-manager',
            target=self.test_manager,
            daemon=False)
        self.manager.start()

        self.launcher = Thread(
            name='test-launcher',
            target=self.launch_testers,
            daemon=False)
        self.launcher.start()

    def launch_testers(self):
        self.tester_threads = []

        for id in range(self.args.manager_testers):
            if self.interrupt.is_set():
                break
            tester = ProxyTester(id, self)
            self.tester_threads.append(tester)
            tester.start()
            # Throttle for database connection pool
            if id < self.args.max_conn:
                time.sleep(0.1)
            else:
                time.sleep(1.0)

    def stop(self):
        self.interrupt.set()
        self.launcher.join()
        log.info('Waiting for proxy tests to finish...')
        self.manager.join()

        for tester in self.tester_threads:
            tester.join()

        log.info('Proxy tester threads shutdown.')

    def test_manager(self):
        """
        Manager main thread for regular statistics logging.
        """
        time.sleep(0.5)
        #log.debug('Loading proxies to test...')
        #self.fill_queue()

        notice_timer = default_timer()
        while True:
            now = default_timer()

            # Print statistics regularly
            if now >= notice_timer + self.args.manager_notice_interval:
                self.print_stats()
                notice_timer = now
                self.reset_notice_stats()

            if self.interrupt.is_set():
                log.debug('Test manager shutting down...')
                break

            # Keep proxy test queue filled
            #self.fill_queue()
            time.sleep(5)

        self.release_queue()

    def print_stats(self):
        log.info('Total tests: %d valid and %d failed.',
                 self.total_success, self.total_fail)
        log.info('Tests in last %ds: %d valid and %d failed.',
                 self.args.manager_notice_interval,
                 self.notice_success, self.notice_fail)
        db_stats = get_connection_stats()
        log.info('Database connections: %d in use and %d available.',
                 db_stats[0], db_stats[1])
        #log.debug('%d proxies queued for testing.', self.queue.qsize())
