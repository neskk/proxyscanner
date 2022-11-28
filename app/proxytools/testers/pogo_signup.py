#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests import Session, Response
from requests.exceptions import (
    ConnectionError, ConnectTimeout, RetryError, TooManyRedirects, RequestException)
from requests.packages import urllib3

from ..models import Proxy, ProxyProtocol, ProxyStatus, ProxyTest
from ..test import Test
from ..utils import export_file

log = logging.getLogger(__name__)


class PoGoSignup(Test):

    STATUS_BANLIST = [403, 409]

    def __init__(self, manager):
        super().__init__(manager)
        self.base_url = 'https://club.pokemon.com/us/pokemon-trainer-club/sign-up/'

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
            self.base_url,
            headers=self.headers,
            timeout=self.args.tester_timeout,
            verify=True)

        return response

    def __skip_test(self, proxy: Proxy) -> bool:
        # if proxy.protocol == ProxyProtocol.SOCKS4:
        #     return True
        return False

    def debug_response(self, response: Response):
        if not self.args.verbose:
            return

        filename = f'{self.args.tmp_path}/pogo_signup.txt'
        info = '\n-----------------\n'
        info += f'Tester Headers:   {self.headers}'
        info += '\n-----------------\n'
        info += f'Request Headers:  {response.request.headers}'
        info += '\n-----------------\n'
        info += f'Response Headers: {response.headers}'
        info += '\n-----------------\n'
        info += 'Response'
        info += '\n-----------------\n'
        info += response.text

        export_file(filename, info)
        log.debug('Response content saved to: %s', filename)

    def validate(self):
        response = self.__request(None)

        if response.status_code != 200:
            log.error('Failed validation request to: %s', self.base_url)
            return False

        proxy_test = ProxyTest(proxy=None, info='PoGo-Login test')
        self.__parse_response(proxy_test, response.text)

        if proxy_test.status != ProxyStatus.OK:
            log.error('Unable to validate response.')
            self.debug_response(response)
            return False

        return True

    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Request PoGo-Signup URL using a proxy and parse response.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        proxy_url = proxy.url()
        if self.__skip_test(proxy):
            log.debug('Skipped PoGo-Signup test for proxy: %s', proxy_url)
            return None

        proxy_test = ProxyTest(proxy=proxy, info='PoGo-Signup test')
        try:
            response = self.__request(proxy_url)

            proxy_test.latency = int(response.elapsed.total_seconds() * 1000)

            if response.status_code in self.STATUS_BANLIST:
                proxy_test.status = ProxyStatus.BANNED
                proxy_test.info = 'Banned status code'
                log.warning('Proxy seems to be banned.')
            if not response.text:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = 'Empty response'
                log.warning('No content in response.')

            elif response.status_code != 200:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = f'Bad status code: {response.status_code}'
                log.warning('Response with bad status code: %s', response.status_code)
            else:
                result = self.__parse_response(proxy_test, response.text)
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

        # Save test results
        proxy_test.save()
        return proxy_test

    def __parse_response(self, proxy_test: ProxyTest, content: str) -> bool:
        """
        Parse PoGo-Signup response content.

        Args:
            content (str): response text content

        Returns:
            bool: true if valid content is found, false otherwise
        """
        soup = BeautifulSoup(content, 'html.parser')
        title = soup.find('title').text
        if title != 'The Official Pokémon Website | Pokemon.com':
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Unexpected page title'
            return False

        proxy_test.status = ProxyStatus.OK
        proxy_test.info = 'Access to PoGo-Signup'

        return True
