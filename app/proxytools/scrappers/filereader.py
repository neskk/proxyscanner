#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from ..proxy_scrapper import ProxyScrapper
from ..utils import load_file

log = logging.getLogger(__name__)


class FileReader(ProxyScrapper):

    def __init__(self):
        super(FileReader, self).__init__('file-reader')

        self.proxy_file = self.args.proxy_file

    def scrap(self):
        proxylist = []
        if not self.proxy_file:
            return proxylist

        proxylist = load_file(self.proxy_file)
        log.info('Read %d proxies from file: %s',
                 len(proxylist), self.proxy_file)

        return proxylist
