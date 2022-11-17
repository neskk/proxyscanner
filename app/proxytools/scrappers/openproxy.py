#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

from bs4 import BeautifulSoup

from ..models import ProxyProtocol
from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class OpenProxySpace(ProxyScrapper):

    def __init__(self, name, protocol):
        super(OpenProxySpace, self).__init__(name, protocol)
        self.base_url = 'https://openproxy.space/list'

    def scrap(self):
        self.setup_session()
        proxylist = []

        url = self.base_url
        html = self.request_url(url, url)

        if html is None:
            log.error('Failed to download webpage: %s', url)
        else:
            log.info('Parsing proxylist from webpage: %s', url)
            proxylist.extend(self.parse_webpage(html))

        self.session.close()
        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        soup = BeautifulSoup(html, 'html.parser')

        scripts = soup.find_all('script')

        for script in scripts:
            code = str(script.string)
            if not code:
                continue

            if not code.startswith('window.__NUXT__'):
                continue

            matches = re.findall(r'\"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\:(\d{1,4})\"', code)
            if not matches:
                log.error('Unable to parse proxylist.')
                break

            for match in matches:
                proxylist.append(f'{match[0]}:{match[1]}')

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist


class OpenProxyHTTP(OpenProxySpace):

    def __init__(self):
        super(OpenProxyHTTP, self).__init__('open-proxy-space-http', ProxyProtocol.HTTP)
        self.base_url = 'https://openproxy.space/list/http/'


class OpenProxySOCKS4(OpenProxySpace):

    def __init__(self):
        super(OpenProxySOCKS4, self).__init__('open-proxy-space-socks4', ProxyProtocol.SOCKS4)
        self.base_url = 'https://openproxy.space/list/socks4'


class OpenProxySOCKS5(OpenProxySpace):

    def __init__(self):
        super(OpenProxySOCKS5, self).__init__('open-proxy-space-socks5', ProxyProtocol.SOCKS5)
        self.base_url = 'https://openproxy.space/list/socks5'
