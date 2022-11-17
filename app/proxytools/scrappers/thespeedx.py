#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging


from ..models import ProxyProtocol
from ..proxy_scrapper import ProxyScrapper
from ..utils import load_file

log = logging.getLogger(__name__)

# https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt
# https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt
# https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt


class TheSpeedX(ProxyScrapper):
    def __init__(self, name, protocol):
        super(TheSpeedX, self).__init__(name, protocol)
        self.base_url = 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/'

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


class TheSpeedXHTTP(TheSpeedX):

    def __init__(self):
        super(TheSpeedXHTTP, self).__init__('the-speed-x-http', ProxyProtocol.HTTP)
        self.base_url += 'http.txt'


class TheSpeedXSOCKS4(TheSpeedX):

    def __init__(self):
        super(TheSpeedXSOCKS4, self).__init__('the-speed-x-socks4', ProxyProtocol.SOCKS4)
        self.base_url += 'socks4.txt'


class TheSpeedXSOCKS5(TheSpeedX):

    def __init__(self):
        super(TheSpeedXSOCKS5, self).__init__('the-speed-x-socks5', ProxyProtocol.SOCKS5)
        self.base_url += 'socks5.txt'
