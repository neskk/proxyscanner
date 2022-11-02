#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import time
from datetime import datetime
from threading import Thread

from playhouse.pool import MaxConnectionsExceeded

from .models import Proxy, ProxyStatus, ProxyTest
from .config import Config

log = logging.getLogger(__name__)


class ProxyTester(Thread):
    """
    Proxy tester thread class.
    Closely tied with ProxyManager class.
    """

    def __init__(self, id: int, manager):
        """
        Abstract class for a proxy tester thread.
        Defines base HTTP headers that can be customized for tests.

        Args:
            manager (TestManager): thread executor and task manager
            id (int): thread ID
        """
        super().__init__(name=f'proxy-tester-{id:03d}')
        self.manager = manager
        self.id = id
        self.args = Config.get_args()
        self.protocols = []  # only test ProxyProtocol in list (none: all)
        self.tests = []
        for test in self.manager.test_classes:
            try:
                self.tests.append(test(manager))
            except Exception:
                log.exception('Failed to initialize test: %s', test)

    def run(self):
        """
        Continuous loop to get and test a proxy from database.
        The proxy is locked for testing using its status.
        Test results are persited and proxy data updated.
        """
        log.debug(f'{self.name} started.')
        while True:
            # Check if work is interrupted
            if self.manager.interrupt.is_set():
                break

            try:
                with Proxy.database().atomic():
                    # Grab and lock proxy
                    proxy = Proxy.get_for_scan(protocols=self.protocols)

                    if proxy is None:
                        log.debug('No proxy to test... Re-checking in 10sec.')
                        # TODO: add config arg for sleep timer
                        time.sleep(10)
                        continue

                    row_count = proxy.lock_for_testing()

                if row_count != 1:
                    log.warning('Failed to acquire a proxy for testing.')
                    time.sleep(random.uniform(0.2, 0.4))
                    continue
            except MaxConnectionsExceeded:
                log.warning('Failed to acquire a database connection.')
                time.sleep(random.uniform(0.2, 0.4))
                continue

            # Release database connection for test duration
            proxy.database().close()

            # Execute tests
            self.__execute_tests(proxy)

        log.debug(f'{self.name} shutdown.')

    def __execute_tests(self, proxy: Proxy):
        for test in self.tests:
            try:
                # Execute test
                proxy_test = test.run(proxy)
                if proxy_test:
                    # Commit proxy test results
                    self.__update(proxy, proxy_test)
            except Exception:
                log.exception('Error executing test: %s', test)

    def __update(self, proxy: Proxy, proxy_test: ProxyTest) -> None:
        """
        Update proxy and notify manager with test results.

        Args:
            proxy (Proxy): proxy being tested
            proxy_test (ProxyTest): test results
        """
        proxy.status = proxy_test.status
        proxy.latency = proxy_test.latency
        proxy.modified = datetime.utcnow()

        if proxy.country is None:
            country = self.manager.ip2location.lookup_country(proxy.ip)
            proxy.country = country

        proxy.save()

        log.debug(f'{proxy_test.info}: {proxy.url()} ({proxy.latency}ms - {proxy.country})')
        if proxy_test.status != ProxyStatus.OK:
            self.manager.mark_fail()
        else:
            self.manager.mark_success()
