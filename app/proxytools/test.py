#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from abc import ABC, abstractmethod

from .config import Config
from .models import Proxy, ProxyTest
from .user_agent import UserAgent
from .utils import http_headers, export_file

from requests.adapters import HTTPAdapter
from requests import Session, Response
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


class Test(ABC):

    STATUS_FORCELIST = [413, 429, 500, 502, 503, 504]

    def __init__(self, manager, name):
        """
        Abstract class for a proxy test request.
        Defines base HTTP headers that can be customized for tests.
        """
        self.args = Config.get_args()
        self.manager = manager
        self.name = name
        self.proxy_judge = Config.get_proxyjudge()

        self.user_agent = UserAgent.generate(self.args.user_agent)
        self.headers = http_headers()
        self.headers['User-Agent'] = self.user_agent

        # https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html
        self.urlib3_retry = Retry(
            allowed_methods=None,  # retry on all HTTP verbs
            total=self.args.tester_retries,
            connect=3,
            read=3,
            redirect=1,
            status=3,
            backoff_factor=self.args.tester_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

    def set_retry(self, total, backoff_factor, status_forcelist):
        self.urlib3_retry = Retry(
            allowed_methods=None,  # retry on all HTTP verbs
            total=total,
            connect=3,
            read=3,
            redirect=1,
            status=3,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist)

    def create_session(self, proxy_url=None) -> Session:
        session = Session()

        session.mount('http://', HTTPAdapter(max_retries=self.urlib3_retry))
        session.mount('https://', HTTPAdapter(max_retries=self.urlib3_retry))

        session.proxies = {'http': proxy_url, 'https': proxy_url}

        return session

    def request(self, url, proxy_url=None) -> Response:
        response = self.create_session(proxy_url).get(
            url,
            headers=self.headers,
            timeout=self.args.tester_timeout,
            verify=True)

        return response

    def debug_response(self, response: Response):
        if not self.args.verbose:
            return

        filename = f'{self.args.download_path}/tester_{self.name}.txt'
        info = '\n-----------------\n'
        info += f'Tester Headers:   {self.headers}'
        info += '\n-----------------\n'
        info += f'Request Headers:  {response.request.headers}'
        info += '\n-----------------\n'
        info += f'Response Headers: {response.headers}'
        info += '\n-----------------\n'
        info += f'Response ({len(response.raw.retries.history)})'
        info += '\n-----------------\n'
        info += response.text

        export_file(filename, info)
        log.debug('Response content saved to: %s', filename)

    @abstractmethod
    def skip_test(self, proxy: Proxy) -> bool:
        return False

    @abstractmethod
    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Perform tests with proxy and return parsed results.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """
        Perform tests without a proxy and return parsed results.

        Returns:
            bool: true if test is working, false otherwise
        """
        pass
