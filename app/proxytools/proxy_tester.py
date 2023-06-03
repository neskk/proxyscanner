import logging
import time
from datetime import datetime
from threading import Thread

from .models import Proxy, ProxyStatus, ProxyTest
from .config import Config
from .db import DatabaseQueue

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
        self.id = id
        self.manager = manager
        self.interrupt = manager.interrupt
        self.args = Config.get_args()
        self.db_queue = DatabaseQueue.get_db_queue()

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
            if self.interrupt.is_set():
                break

            if self.db_queue.interrupt.is_set():
                break

            proxy = self.db_queue.get_proxy()

            if proxy is None:
                log.debug('No proxy to test...')
                time.sleep(30.0)
                continue

            # Execute tests
            results = self.execute_tests(proxy)

            # Update database with test results
            self.evaluate_results(proxy, results)
            self.db_queue.update_proxy(proxy)

        log.debug(f'{self.name} shutdown.')

    def evaluate_results(self, proxy: Proxy, results: list) -> None:
        """
        Update proxy model object with data from test results.

        Args:
            proxy (Proxy): proxy that was tested
            results (list(ProxyTest)): proxy test results
        """
        if proxy.country is None:
            country = self.manager.ip2location.lookup_country(proxy.ip)
            proxy.country = country

        total_latency = 0
        for proxy_test in results:
            total_latency += proxy_test.latency

        proxy.latency = int(total_latency / len(results))
        proxy.status = results[-1].status
        proxy.modified = datetime.utcnow()
        # log.debug(f'Tested Proxy #{proxy.id}: {proxy_test.info} - {proxy.latency}ms')

    def update_stats(self, proxy: Proxy, proxy_test: ProxyTest) -> None:
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

    def execute_tests(self, proxy: Proxy):
        results = []
        for test in self.tests:
            test_name = test.__class__.__name__
            try:
                if test.skip_test(proxy):
                    log.debug('Skipped %s test for proxy: %s', test.name, proxy.url())
                    continue

                # log.debug(f'Running test {test.name} on Proxy #{proxy.id}: {proxy.url()}')
                proxy_test = test.run(proxy)
                if not proxy_test:
                    log.error('Proxy test %s returned no results.', test_name)
                    continue

                results.append(proxy_test)
                self.update_stats(proxy, proxy_test)
                self.db_queue.update_proxytest(proxy_test)

                # Stop if proxy fails a test
                if not self.args.tester_force and proxy_test.status != ProxyStatus.OK:
                    break

                # Check if work is interrupted
                if self.interrupt.is_set():
                    break
            except Exception:
                log.exception('Error executing test: %s', test_name)
                self.interrupt.set()
                break

        # Update proxy status with results from executed tests
        if not results:
            results.append(ProxyTest(
                proxy=proxy,
                info='Not tested',
                status=ProxyStatus.ERROR))

        return results
