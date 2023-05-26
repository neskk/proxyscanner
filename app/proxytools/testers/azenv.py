#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from requests.exceptions import (
    ConnectionError, ConnectTimeout, RetryError, TooManyRedirects, RequestException)

from ..models import Proxy, ProxyStatus, ProxyTest
from ..test import Test

log = logging.getLogger(__name__)


class AZenv(Test):

    STATUS_BANLIST = [403, 409]

    def __init__(self, manager):
        super().__init__(manager, 'azenv')
        self.base_url = self.proxy_judge

    def skip_test(self, proxy: Proxy) -> bool:
        return False

    def validate(self):
        response = self.request(self.base_url, None)

        if response.status_code != 200:
            log.error('Failed validation request to: %s', self.base_url)
            return False

        headers = self.parse_response(response.text)
        if not headers.get('REMOTE_ADDR') or not headers.get('USER_AGENT'):
            log.error('Unable to validate response.')
            self.debug_response(response)
            return False

        return True

    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Request proxy judge AZenv URL using a proxy and parse response.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        proxy_url = proxy.url()
        proxy_test = ProxyTest(proxy=proxy, info='AZenv test')
        try:
            response = self.request(self.base_url, proxy_url)

            proxy_test.latency = int(response.elapsed.total_seconds() * 1000)

            if response.status_code in self.STATUS_BANLIST:
                proxy_test.status = ProxyStatus.BANNED
                proxy_test.info = 'Banned status code'
                log.warning('Proxy seems to be banned.')
            elif not response.text:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = 'Empty response'
                log.warning('No content in response.')
            elif response.status_code != 200:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = f'Bad status code: {response.status_code}'
                log.warning('Response with bad status code: %s', response.status_code)
            else:
                headers = self.parse_response(response.text)
                result = self.analyze_headers(proxy_test, headers)
                if not result:
                    log.debug('Failed to parse response with: %s', proxy_url)

            response.close()
        except ConnectTimeout:
            proxy_test.status = ProxyStatus.TIMEOUT
            proxy_test.info = 'Connection timed out'
        except (ConnectionError, TooManyRedirects, RetryError) as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Failed to connect - ' + type(e).__name__
        except RequestException as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Request exception - ' + type(e).__name__
        except Exception as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Unexpected error - ' + type(e).__name__
            log.exception('Unexpected error: %s', e)

        return proxy_test

    def parse_response(self, content: str) -> dict:
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
                    result[keyword] = line.split('=')[1].strip()
                    break  # jump to next line

        return result

    def analyze_headers(self, proxy_test: ProxyTest, headers: dict) -> bool:
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
        for value in headers.values():
            if self.args.local_ip in value:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = 'Non-anonymous proxy'
                return False

        if headers.get('USER_AGENT') != self.user_agent:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Bad user-agent'
            result = False
        else:
            proxy_test.status = ProxyStatus.OK
            proxy_test.info = 'Anonymous proxy'

        return result
