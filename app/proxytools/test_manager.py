#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
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

        self.local_ip = self.find_local_ip()
        self.plan_test_cycle()

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
        except Exception:
            log.exception('Failed to connect to proxy judge.')

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

    def start(self):
        # Start proxy manager thread.
        self.manager = Thread(
            name='test-manager',
            target=self.__test_manager,
            daemon=False)
        self.manager.start()

        self.tester_threads = []

        # Start proxy tester threads.
        for id in range(self.args.manager_testers):
            tester = ProxyTester(id, self)

            self.tester_threads.append(tester)

            tester.start()
            time.sleep(0.1)

    def stop(self):
        self.interrupt.set()

        for thread in self.tester_threads:
            thread.join()

        self.manager.join()

    def __test_manager(self):
        """
        Manager main thread for regular statistics logging.
        """
        notice_timer = default_timer()
        while True:
            now = default_timer()
            # Print statistics regularly.
            if now >= notice_timer + self.args.manager_notice_interval:
                log.info('Tested a total of %d good and %d bad proxies.',
                         self.total_success, self.total_fail)
                log.info('Tested %d good and %d bad proxies in last %ds.',
                         self.notice_success, self.notice_fail,
                         self.args.manager_notice_interval)

                notice_timer = now
                self.reset_notice_stats()

            if self.interrupt.is_set():
                log.debug('Proxy manager shutting down...')
                break

            time.sleep(5)
