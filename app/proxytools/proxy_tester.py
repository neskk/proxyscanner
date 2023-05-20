import logging
import random
import time
from datetime import datetime, timedelta
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
                Proxy.database().connect(reuse_if_open=True)
                # Grab a proxy for testing
                proxy = Proxy.get_for_scan(protocols=self.args.proxy_protocol)

                if proxy is None:
                    log.debug('No proxy to test...')
                    time.sleep(random.uniform(5.0, 15.0))
                    continue

                # Lock proxy for testing
                row_count = proxy.lock_for_testing()
                if row_count != 1:
                    log.warning(f'Failed to lock Proxy #{proxy.id} for testing.')
                    continue

                # Check if proxy should be removed
                if self.cleanup(proxy):
                    continue

            except DatabaseError as e:
                log.critical(f'Failed to update Proxy #{proxy.id}: {e}')
            except MaxConnectionsExceeded as e:
                log.critical(
                    f'Failed to acquire a database connection: {e}\n'
                    'Increase max DB connections or decrease # of threads!')
                break
            finally:
                Proxy.database().close()

            # Execute tests
            results = self.execute_tests(proxy)

            # Update database with test results

            if not self.update_database(proxy, results):
                break

        Proxy.database().close()
        log.debug(f'{self.name} shutdown.')

    def cleanup(self, proxy: Proxy) -> bool:
        """
        Tests if proxy is old and not worth testing.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            bool: True if proxy was deleted, False otherwise
        """
        analysis_period = self.args.cleanup_period
        min_age = datetime.utcnow() - timedelta(days=analysis_period)

        # Do not evaluate proxies before a cleanup period has passed
        if proxy.created > min_age:
            return False

        # Check test count during cleanup period
        test_count = ProxyTest.all_tests(proxy.id, age_days=analysis_period).count()
        if test_count < self.args.cleanup_test_count:
            return False

        # Check fail ratio during cleanup period
        fail_count = ProxyTest.failed_tests(proxy.id, age_days=analysis_period).count()
        fail_ratio = fail_count / test_count
        if fail_ratio < self.args.cleanup_fail_ratio:
            return False

        return self.delete_proxy(proxy)

    def delete_proxy(self, proxy: Proxy):
        row_count = proxy.delete_instance()
        if row_count != 1:
            log.warning(f'Failed to delete Proxy #{proxy.id}.')
            return False

        log.info(f'Deleted Proxy #{proxy.id} - failed '
                 f'{proxy.fail_count} out of {proxy.test_count} tests.')
        return True

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

    def update_database(self, proxy: Proxy, results: list) -> bool:
        """
        Update database with new test results.

        Args:
            proxy (Proxy): proxy being tested
            results (list(ProxyTest)): proxy test results
        """
        try:
            proxy.database().connect()

            for proxy_test in results:
                if proxy_test.is_dirty():
                    proxy_test.save()

            proxy.save()
            log.debug(
                f'Updated Proxy #{proxy.id} - {proxy.url()} - '
                f'({proxy.latency}ms - {proxy.country}) - '
                f'{proxy.test_score():.2f}% ({proxy.test_count} tests)')
            return True
        except DatabaseError as e:
            log.critical(f'Failed to update Proxy #{proxy.id}: {e}')
        except MaxConnectionsExceeded as e:
            log.critical(
                f'Unable to update database: {e}\n'
                'Increase max DB connections or decrease # of threads!')
        finally:
            proxy.database().close()  # force connection recycling

        return False

    def update(self, proxy: Proxy, results: list) -> bool:
        """
        Update proxy and test data with results.

        Args:
            proxy (Proxy): proxy being tested
            results (list(ProxyTest)): proxy test results
        """
        self.evaluate_results(proxy, results)
        for i in range(5):
            if self.update_database(proxy, results):
                return True
            time.sleep(3.0)

        return False

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

                # Update proxy status with results from the last executed test
                results.append(proxy_test)
                self.update_stats(proxy, proxy_test)

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

        return results
