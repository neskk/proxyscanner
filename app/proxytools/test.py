#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from abc import ABC, abstractmethod

from .config import Config
from .models import Proxy, ProxyTest
from .user_agent import UserAgent

log = logging.getLogger(__name__)


class Test(ABC):

    STATUS_FORCELIST = [500, 502, 503, 504]

    BASE_HEADERS = {
        'Upgrade-Insecure-Requests': '1',
        'Connection': 'close',
        'Accept': ('text/html,application/xhtml+xml,'
                   'application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'),
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'br, gzip, deflate'
    }

    def __init__(self, manager):
        """
        Abstract class for a proxy test.
        Defines base HTTP headers that can be customized for tests.
        """
        self.args = Config.get_args()
        self.user_agent = UserAgent.generate(self.args.user_agent)
        self.headers = self.BASE_HEADERS.copy()
        self.headers['User-Agent'] = self.user_agent
        self.local_ip = manager.local_ip

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
