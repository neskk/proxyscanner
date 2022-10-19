#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import random
import time
import requests

from datetime import datetime

from playhouse.pool import MaxConnectionsExceeded
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ConnectTimeout, RetryError, TooManyRedirects
from requests.packages import urllib3
from urllib.parse import urlparse

from ..models import Proxy, ProxyStatus, ProxyTest
from ..proxy_tester import ProxyTester
from ..utils import export_file

log = logging.getLogger(__name__)


class AZenv(ProxyTester):

    STATUS_FORCELIST = [500, 502, 503, 504]
    STATUS_BANLIST = [403, 409]

    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:105.0) Gecko/20100101 Firefox/105.0'
    BASE_HEADERS = {
        'Upgrade-Insecure-Requests': '1',
        'Connection': 'close',
        'Accept': ('text/html,application/xhtml+xml,'
                   'application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'),
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'br, gzip, deflate'
    }

    def __init__(self, manager, id):
        super().__init__(manager, id)

        # Customize headers for test
        self.headers = self.BASE_HEADERS.copy()
        self.headers['Host'] = urlparse(self.args.proxy_judge).hostname

        # https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html
        self.urlib3_retry = urllib3.Retry(
            total=self.args.tester_retries,
            backoff_factor=self.args.tester_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

    def run(self):
        log.info('AZenv proxy tester started.')
        while True:
            if self.manager.interrupt.is_set():
                break

            try:
                # Grab and lock proxy
                with Proxy.database().atomic():

                    proxy = Proxy.get_for_scan()

                    if proxy is None:
                        log.debug('No Proxy needs testing. Re-checking in 10sec.')
                        # TODO: add config arg for sleep timer
                        time.sleep(10)
                        continue

                    row_count = proxy.lock_for_testing()

                if row_count != 1:
                    log.warning('Failed to acquire a proxy for testing.')
                    time.sleep(random.random())
                    continue
            except MaxConnectionsExceeded:
                log.warning('Failed to acquire a database connection.')
                time.sleep(10)
                continue

            # Execute and parse proxy test
            proxy_test = self.__test(proxy)

            # Update and release proxy
            proxy.status = proxy_test.status
            proxy.latency = proxy_test.latency
            proxy.modified = datetime.utcnow()

            if proxy.country is None:
                # TODO: this might get refactored to proxy_tester
                country = self.manager.ip2location.lookup_country(proxy.ip)
                proxy.country = country

            proxy.save()
            Proxy.database().close()

            # Update manager stats
            log.debug(f'{proxy_test.info}: {proxy.url()} ({proxy.latency}ms - {proxy.country})')
            if proxy_test.status != ProxyStatus.OK:
                self.manager.mark_fail()
            else:
                self.manager.mark_success()

    def __session(self, proxy_url):
        session = requests.Session()

        session.mount('http://', HTTPAdapter(max_retries=self.urlib3_retry))
        session.mount('https://', HTTPAdapter(max_retries=self.urlib3_retry))

        session.proxies = {'http': proxy_url, 'https': proxy_url}

        return session

    # Make HTTP request using selected proxy.
    def __test(self, proxy: Proxy) -> ProxyTest:
        """
        Request proxy judge AZenv URL using a proxy and parse response.
        Update database with test data for current proxy.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: resulting test data model
        """
        # Initialize new proxy test model
        proxy_test = ProxyTest(proxy=proxy, info="AZenv test")
        proxy_url = proxy.url()

        try:
            response = self.__session(proxy_url).get(
                self.args.proxy_judge,
                headers=self.headers,
                timeout=self.args.tester_timeout,
                verify=False)

            proxy_test.latency = int(response.elapsed.total_seconds() * 1000)

            if response.status_code in self.STATUS_BANLIST:
                proxy_test.status = ProxyStatus.BANNED
                proxy_test.info = "Banned status code"
                log.warning('Proxy seems to be banned.')
            elif not response.text:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = "Empty response"
                log.warning('No content in response.')
            else:
                headers = self.__parse_response(response.text)
                result = self.__analyze_headers(proxy_test, headers)
                if not result and self.args.verbose:
                    filename = f'{self.args.download_path}/response_azenv_{proxy.ip}.txt'

                    export_file(filename, response.text)
                    log.debug('Response content saved to: %s', filename)

            response.close()
        except ConnectTimeout:
            proxy_test.status = ProxyStatus.TIMEOUT
            proxy_test.info = 'Connection timed out'
        except (ConnectionError, TooManyRedirects, RetryError) as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Failed to connect - ' + type(e).__name__
        except Exception as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Unexpected error - ' + type(e).__name__
            log.exception('Unexpected error: %s', e)

        # Save current proxy test results
        proxy_test.save()
        return proxy_test

    def __parse_response(self, content: str) -> dict:
        """
        Parse AZenv response content for useful HTTP headers.

        Args:
            content (str): response text content

        Returns:
            dict: header values found in content
        """
        result = {}
        keywords = [
            'REMOTE_ADDR',
            'USER_AGENT',
            'FORWARDED_FOR',
            'FORWARDED',
            'CLIENT_IP',
            'X_FORWARDED_FOR',
            'X_FORWARDED',
            'X_CLUSTER_CLIENT_IP']

        for line in content.split('\n'):
            line_upper = line.upper()
            for keyword in keywords:
                if keyword in line_upper:
                    result[keyword] = line.split(' = ')[1]
                    break  # jump to next line

        return result

    def __analyze_headers(self, proxy_test: ProxyTest, headers: dict) -> bool:
        """
        Check header values for current local IP.
        Update proxy test based on parsed HTTP headers.

        Args:
            proxy_test (ProxyTest): proxy test model being updated
            headers (dict): parsed headers from response

        Returns:
            bool: True if analysis is successful, False otherwise (debug info)
        """
        result = True
        if not headers:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Error parsing response'
            return False

        # search for local IP
        local_ip = self.manager.local_ip
        for value in headers.values():
            if local_ip in value:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = 'Non-anonymous proxy'
                return False

        if headers.get('USER_AGENT') != self.USER_AGENT:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Bad user-agent'
            result = False
        else:
            proxy_test.status = ProxyStatus.OK
            proxy_test.info = 'Anonymous proxy'

        return result
