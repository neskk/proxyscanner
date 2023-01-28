#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup
from requests.exceptions import (
    ConnectionError, ConnectTimeout, RetryError, TooManyRedirects, RequestException)

from ..models import Proxy, ProxyStatus, ProxyTest
from ..test import Test

log = logging.getLogger(__name__)


class PoGoSignup(Test):

    STATUS_BANLIST = [403, 409]

    def __init__(self, manager):
        super().__init__(manager, 'pogo-signup')
        self.base_url = 'https://club.pokemon.com/us/pokemon-trainer-club/sign-up/'

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
        self.parse_response(proxy_test, response.text)

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
        proxy_test = ProxyTest(proxy=proxy, info='PoGo-Signup test')
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
                result = self.parse_response(proxy_test, response.text)
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
        proxy_test.database().close()
        return proxy_test

    def parse_response(self, proxy_test: ProxyTest, content: str) -> bool:
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
