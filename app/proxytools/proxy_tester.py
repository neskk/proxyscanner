#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from threading import Thread

from playhouse.pool import MaxConnectionsExceeded

from .models import Proxy, ProxyStatus, ProxyTest
from .config import Config
from .user_agent import UserAgent


log = logging.getLogger(__name__)


class ProxyTester(ABC, Thread):
    """
    Proxy tester thread class.
    Closely tied with ProxyManager class.
    """
    STATUS_FORCELIST = [500, 502, 503, 504]

    BASE_HEADERS = {
        'Upgrade-Insecure-Requests': '1',
        'Connection': 'close',
        'Accept': ('text/html,application/xhtml+xml,'
                   'application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'),
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'br, gzip, deflate'
    }

    def __init__(self, manager, id: int):
        """
        Abstract class for a proxy tester thread.
        Defines base HTTP headers that can be customized for tests.

        Args:
            manager (TestManager): thread executor and task manager
            id (int): thread ID
        """
        ABC.__init__(self)  # explicit calls without super
        Thread.__init__(self, name=f'proxy-tester-{id:03d}')
        self.manager = manager
        self.id = id
        self.args = Config.get_args()
        self.user_agent = UserAgent.generate(self.args.user_agent)
        self.headers = self.BASE_HEADERS.copy()
        self.headers['User-Agent'] = self.user_agent

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
                    proxy = self.get_proxy()

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
            try:
                # Execute and parse proxy test
                proxy_test = self.test(proxy)
                self.__update(proxy, proxy_test)
            except Exception:
                log.exception('Unexcepted error!')

        log.debug(f'{self.name} shutdown.')

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

    @abstractmethod
    def get_proxy(self) -> Proxy:
        """
        Fetch a single Proxy from the database for testing.

        Returns:
            Proxy: selected for testing
        """
        pass

    @abstractmethod
    def test(self, proxy: Proxy) -> ProxyTest:
        """
        Perform tests with proxy and return parsed results.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        pass
