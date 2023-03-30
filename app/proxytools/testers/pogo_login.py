#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from requests import Response
from requests.exceptions import (
    ConnectionError, ConnectTimeout, RetryError, TooManyRedirects, RequestException)

from ..models import Proxy, ProxyStatus, ProxyTest
from ..test import Test
log = logging.getLogger(__name__)


class PoGoLogin(Test):

    STATUS_BANLIST = [403, 409]

    USER_AGENT = 'pokemongo/0 CFNetwork/897.1 Darwin/17.5.0'
    UNITY_VERSION = '2017.1.2f1'

    POGO_HEADERS = {
        'Connection': 'close',
        'Accept': '*/*',
        'User-Agent': USER_AGENT,
        'Accept-Language': 'en-us',
        'Accept-Encoding': 'br, gzip, deflate',
        'X-Unity-Version': UNITY_VERSION,
    }

    def __init__(self, manager):
        super().__init__(manager, 'pogo-login')
        # self.headers = self.POGO_HEADERS.clone()
        self.base_url = ('https://sso.pokemon.com/sso/login?service='
                         'https%3A%2F%2Fsso.pokemon.com%2Fsso%2Foauth2.0%2F'
                         'callbackAuthorize&locale=en_US')

    def skip_test(self, proxy: Proxy) -> bool:
        # if proxy.protocol == ProxyProtocol.SOCKS4:
        #     return True
        return False

    def validate(self):
        response = self.request(self.base_url, None)

        if response.status_code != 200:
            log.error('Failed validation request to: %s', self.base_url)
            return False

        proxy_test = ProxyTest(proxy=None, info='PoGo-Login test')
        self.parse_response(proxy_test, response)

        if proxy_test.status != ProxyStatus.OK:
            log.error('Unable to validate response.')
            self.debug_response(response)
            return False

        return True

    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Request PoGo-Login URL using a proxy and parse response.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        proxy_url = proxy.url()
        proxy_test = ProxyTest(proxy=proxy, info='PoGo-Login test')
        try:
            response = self.request(self.base_url, proxy_url)

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
                result = self.parse_response(proxy_test, response)
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
        self.save(proxy_test)

        return proxy_test

    def parse_response(self, proxy_test: ProxyTest, response: Response) -> bool:
        """
        Parse PoGo-Login response content.

        Args:
            content (str): response text content

        Returns:
            bool: true if valid content is found, false otherwise
        """
        json = response.json()
        # { "lt": "LT-34571919-WbnEHMLcdTP7SHsNWZhveQU4ZQKsq9", "execution": "e5s1" }

        if json.get('lt') and json.get('execution'):
            proxy_test.status = ProxyStatus.OK
            proxy_test.info = 'Access to PoGo-Login'
            return True

        return False
