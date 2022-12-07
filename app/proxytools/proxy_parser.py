#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from .config import Config
from .proxy_scrapper import ProxyScrapper

from .scrappers import CLASSES as SCRAPPER_CLASSES


log = logging.getLogger(__name__)


class ProxyParser():

    def __init__(self):
        self.args = Config.get_args()

        args = self.args
        self.debug = args.verbose
        self.download_path = args.download_path
        self.refresh_interval = args.proxy_refresh_interval

        # Configure proxy scrappers
        self.scrappers = {}
        self.load_scrappers()

    def load_scrappers(self):
        if not self.args.proxy_scrap:
            return

        for scrapper_cls in SCRAPPER_CLASSES:
            # Use all scrappers if no protocol is specified
            if self.args.proxy_protocol is None:
                self.register_scrapper(scrapper_cls)
                continue

            # Register scrappers with unspecified protocol
            if scrapper_cls.get_protocol() is None:
                self.register_scrapper(scrapper_cls)
                continue

            # Register scrappers with specified protocol
            if self.args.proxy_protocol == scrapper_cls.get_protocol():
                self.register_scrapper(scrapper_cls)

    def register_scrapper(self, scrapper_cls):
        try:
            scrapper = scrapper_cls()
        except RuntimeError as e:
            log.debug(e)
        self.scrappers[scrapper.name] = scrapper

    def unregister_scrapper(self, scrapper: ProxyScrapper):
        self.scrappers.pop(scrapper.name, None)

    def load_proxylist(self):
        if not self.scrappers:
            return

        for name, scrapper in self.scrappers.items():
            scrapper.start()
            scrapper.join()
