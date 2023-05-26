#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import time

from timeit import default_timer
from threading import Event, Lock, Thread

from requests.packages import urllib3

from .ip2location import IP2LocationDatabase
from .config import Config
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

        self.plan_test_cycle()

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

    def start(self):
        # Start test manager thread
        self.manager_thread = Thread(
            name='test-manager',
            target=self.test_manager,
            daemon=False)
        self.manager_thread.start()

    def launch_testers(self):
        self.tester_threads = []
        time.sleep(5.0)
        for id in range(self.args.manager_testers):
            tester_thread = ProxyTester(id, self)
            self.tester_threads.append(tester_thread)
            tester_thread.start()

    def stop(self):
        self.interrupt.set()
        self.manager_thread.join()
        log.info('Waiting for proxy tests to finish...')
        for tester in self.tester_threads:
            tester.join()
        log.info('Proxy tester threads shutdown.')

    def test_manager(self):
        """
        Manager main thread for regular statistics logging.
        """
        self.launch_testers()

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

            time.sleep(5)

    def print_stats(self):
        log.info('Total tests: %d valid and %d failed.',
                 self.total_success, self.total_fail)
        log.info('Tests in last %ds: %d valid and %d failed.',
                 self.args.manager_notice_interval,
                 self.notice_success, self.notice_fail)
