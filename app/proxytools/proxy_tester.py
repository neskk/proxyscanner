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

    def __init__(self, manager, id):
        super().__init__(name=f'proxy-tester-{id:03d}')
        self.id = id
        self.manager = manager
        self.args = Config.get_args()
        self.user_agent = UserAgent.generate(self.args.user_agent)
        self.headers = self.BASE_HEADERS
        self.headers['User-Agent'] = self.user_agent
        self.protocols = []

    def run(self):
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
    def test(self, proxy: Proxy) -> ProxyTest:
        pass
