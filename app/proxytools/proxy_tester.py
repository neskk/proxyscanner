#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import time
from datetime import datetime
from threading import Thread

from peewee import DatabaseError
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
        super().__init__(name=f'proxy-tester-{id:03d}', daemon=False)
        self.manager = manager
        self.id = id
        self.args = Config.get_args()
        # Test only protocols in list (empty: all)
        self.protocols = []  # list(ProxyProtocol)
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

                # Check if proxy should be removed
                if self.__cleanup(proxy):
                    continue

            except (DatabaseError, MaxConnectionsExceeded) as e:
                log.warning('Failed to acquire a database connection: %s', e)
                time.sleep(random.uniform(5.0, 15.0))
                continue

            # Release database connection for test duration
            proxy.database().close()

            # Execute tests
            self.__execute_tests(proxy)

        log.debug(f'{self.name} shutdown.')

    def __execute_tests(self, proxy: Proxy):
        results = []
        for test in self.tests:
            test_name = test.__class__.__name__
            try:
                if test.skip_test(proxy):
                    log.debug('Skipped %s test for proxy: %s', test.name, proxy.url())
                    continue

                proxy_test = test.run(proxy)
                if not proxy_test:
                    log.error('Proxy test %s returned no results.', test_name)
                    continue

                # Update proxy status with results from the last executed test
                results.append(proxy_test)
                self.__stats(proxy, proxy_test)

                # Stop if proxy fails a test
                if not self.args.tester_force and proxy_test.status != ProxyStatus.OK:
                    break

                # Check if work is interrupted
                if self.manager.interrupt.is_set():
                    break
            except Exception:
                log.exception('Error executing test: %s', test_name)
                self.manager.interrupt.set()
                break

        # Update proxy status with results from executed tests
        if not results:
            results.append(ProxyTest(
                proxy=proxy,
                info='Not tested',
                status=ProxyStatus.ERROR))

        self.__update(proxy, results)

    def __stats(self, proxy: Proxy, proxy_test: ProxyTest) -> None:
        """
        Notify manager with test results.

        Args:
            proxy (Proxy): proxy being tested
            proxy_test (ProxyTest): test results
        """

        proxy.test_count += 1
        if proxy_test.status != ProxyStatus.OK:
            self.manager.mark_fail()
            proxy.fail_count += 1
        else:
            self.manager.mark_success()

    def __cleanup(self, proxy: Proxy) -> bool:
        analysis_period = self.args.cleanup_period

        # Check test count during cleanup period
        test_count = ProxyTest.all_tests(proxy.id, age_days=analysis_period).count()
        if test_count < self.args.cleanup_test_count:
            return False

        # Check fail ratio during cleanup period
        fail_count = ProxyTest.failed_tests(proxy.id, age_days=analysis_period).count()
        fail_ratio = fail_count / test_count
        if fail_ratio < self.args.cleanup_fail_ratio:
            return False

        row_count = proxy.delete_instance()
        proxy.database().close()

        if row_count != 1:
            log.warning(f'Failed to delete Proxy #{proxy.id}.')
            return True

        log.debug(f'Deleted Proxy #{proxy.id} - '
                  f'failed {fail_ratio*100:.2f}% ({fail_count} / {test_count}).')

        return True

    def __update(self, proxy: Proxy, results: list) -> None:
        """
        Update proxy with test results.

        Args:
            proxy (Proxy): proxy being tested
            results (list(ProxyTest)): proxy test results
        """
        proxy_test = results[-1]

        proxy.status = proxy_test.status
        proxy.latency = proxy_test.latency
        proxy.modified = datetime.utcnow()

        if proxy.country is None:
            country = self.manager.ip2location.lookup_country(proxy.ip)
            proxy.country = country

        try:
            proxy.save()
            proxy.database().close()
        except Exception as e:
            log.error(f'Failed to update Proxy #{proxy.id}: {e}')
            return

        log.debug(f'Updated Proxy #{proxy.id} - '
                  f'{proxy_test.info}: {proxy.url()} - '
                  f'({proxy.latency}ms - {proxy.country}) - '
                  f'{proxy.test_score():.2f}% ({proxy.test_count} tests)')
