#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from requests.adapters import HTTPAdapter
from requests import Session, Response
from requests.exceptions import (
    ConnectionError, ConnectTimeout, RetryError, TooManyRedirects, RequestException)
from requests.packages import urllib3

from ..models import Proxy, ProxyProtocol, ProxyStatus, ProxyTest
from ..test import Test
from ..utils import export_file

log = logging.getLogger(__name__)


class AZenv(Test):

    STATUS_BANLIST = [403, 409]

    def __init__(self, manager):
        super().__init__(manager)

        # https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html
        self.urlib3_retry = urllib3.Retry(
            total=self.args.tester_retries,
            backoff_factor=self.args.tester_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

    def __session(self, proxy_url) -> Session:
        session = Session()

        session.mount('http://', HTTPAdapter(max_retries=self.urlib3_retry))
        session.mount('https://', HTTPAdapter(max_retries=self.urlib3_retry))

        session.proxies = {'http': proxy_url, 'https': proxy_url}

        return session

    def __request(self, proxy_url: str) -> Response:
        response = self.__session(proxy_url).get(
            self.args.proxy_judge,
            headers=self.headers,
            timeout=self.args.tester_timeout,
            verify=False)  # ignore SSL errors

        return response

    def __skip_test(self, proxy: Proxy) -> bool:
        # if proxy.protocol == ProxyProtocol.SOCKS4:
        #     return True
        return False

    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Request proxy judge AZenv URL using a proxy and parse response.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        proxy_url = proxy.url()
        if self.__skip_test(proxy):
            log.debug('Skipped AZenv test for proxy: %s', proxy_url)
            return None

        proxy_test = ProxyTest(proxy=proxy, info='AZenv test')
        try:
            response = self.__request(proxy_url)

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
                headers = self.__parse_response(response.text)
                result = self.__analyze_headers(proxy_test, headers)

                # TODO: improve this debug
                if not result and self.args.verbose:
                    filename = f'{self.args.tmp_path}/azenv_{proxy.id}.txt'
                    info = f'{proxy.id} - {proxy_url} - {proxy_test.info}\n'
                    info += '\n-----------------\n'
                    info += f'Tester Headers:   {self.headers}\n'
                    info += '\n-----------------\n'
                    info += f'Request Headers:  {response.request.headers}\n'
                    info += '\n-----------------\n'
                    info += f'Parsed Headers:   {headers}\n'
                    info += '\n-----------------\n'
                    info += f'Response Headers: {response.headers}\n'
                    info += '\n-----------------\n\n'
                    export_file(filename, info + response.text)
                    log.debug('Response content saved to: %s', filename)

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

        # Save test results
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
                    result[keyword] = line.split('=')[1].strip()
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
        for value in headers.values():
            if self.local_ip in value:
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
