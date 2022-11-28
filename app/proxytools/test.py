#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from abc import ABC, abstractmethod

from .config import Config
from .models import Proxy, ProxyTest
from .user_agent import UserAgent
from .utils import http_headers

log = logging.getLogger(__name__)


class Test(ABC):

    STATUS_FORCELIST = [500, 502, 503, 504]

    def __init__(self, manager):
        """
        Abstract class for a proxy test.
        Defines base HTTP headers that can be customized for tests.
        """
        self.args = Config.get_args()
        self.user_agent = UserAgent.generate(self.args.user_agent)
        self.headers = http_headers()
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

    @abstractmethod
    def validate(self) -> bool:
        """
        Perform tests without a proxy and return parsed results.

        Returns:
            bool: true if test is working, false otherwise
        """
        pass
