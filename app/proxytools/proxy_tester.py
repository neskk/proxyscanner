#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from threading import Thread

from .config import Config


log = logging.getLogger(__name__)


class ProxyTester(Thread):
    """
    Proxy tester thread class.
    Closely tied with ProxyManager class.
    """

    def __init__(self, manager, id):
        super().__init__(name=f'proxy-tester-{id:03d}')
        self.id = id
        self.manager = manager
        self.args = Config.get_args()


"""
    # Override the run() function of Thread class
    def run(self):
        # We have a ref to args, manager and retries available
        while True:
            if self.manager.interrupt.is_set():
                break

            # 1. Grab and lock proxy
            # 2. Lock proxy
            # 3. Execute and parse proxy test
            # 4. Update and release proxy
"""
