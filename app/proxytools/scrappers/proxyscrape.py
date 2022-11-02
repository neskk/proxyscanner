#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

from bs4 import BeautifulSoup

from ..proxy_scrapper import ProxyScrapper
from ..utils import load_file

log = logging.getLogger(__name__)

# https://api.proxyscrape.com/?request=getproxies&proxytype=http&timeout=10000&country=all&ssl=all&anonymity=anonymous
# https://api.proxyscrape.com/?request=getproxies&proxytype=socks4&timeout=10000&country=all
# https://api.proxyscrape.com/?request=getproxies&proxytype=socks5&timeout=10000&country=all


class ProxyScrape(ProxyScrapper):

    def __init__(self, name):
        super(ProxyScrape, self).__init__(name)
        self.base_url = 'https://api.proxyscrape.com/?request=getproxies'

    def download_proxylist(self, url):
        proxylist = []

        log.info('Downloading proxylist from: %s', url)
        filename = '{}/{}.txt'.format(self.download_path, self.name)
        if not self.download_file(url, filename):
            log.error('Failed proxylist download: %s', url)
            return proxylist

        proxylist = load_file(filename)
        return proxylist

    def scrap(self):
        self.setup_session()
        proxylist = self.download_proxylist(self.base_url)
        self.session.close()
        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist


class ProxyScrapeHTTP(ProxyScrape):

    def __init__(self):
        super(ProxyScrapeHTTP, self).__init__('proxy-scrape-http')
        self.base_url += '&proxytype=http&timeout=10000&country=all&ssl=all&anonymity=anonymous'


class ProxyScrapeSOCKS4(ProxyScrape):

    def __init__(self):
        super(ProxyScrapeSOCKS4, self).__init__('proxy-scrape-socks4')
        self.base_url += '&proxytype=socks4&timeout=10000&country=all'


class ProxyScrapeSOCKS5(ProxyScrape):

    def __init__(self):
        super(ProxyScrapeSOCKS5, self).__init__('proxy-scrape-socks5')
        self.base_url += '&proxytype=socks5&timeout=10000&country=all'
