#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..models import ProxyProtocol
from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Socksproxy(ProxyScrapper):

    def __init__(self):
        super(Socksproxy, self).__init__('socksproxy-net', ProxyProtocol.SOCKS5)
        self.base_url = 'https://www.socks-proxy.net/'

    def scrap(self):
        self.setup_session()
        proxylist = []

        html = self.request_url(self.base_url)
        if html is None:
            log.error('Failed to download webpage: %s', self.base_url)
        else:
            log.info('Parsing proxylist from webpage: %s', self.base_url)
            soup = BeautifulSoup(html, 'html.parser')
            proxylist = self.parse_webpage(soup)

        self.session.close()
        return proxylist

    def parse_webpage(self, soup):
        proxylist = []

        table = soup.select_one('div.fpl-list table')

        if not table:
            log.error('Unable to find proxylist table.')
            return proxylist

        table_rows = table.find_all('tr')
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 8:
                continue

            ip = columns[0].get_text().strip()
            port = columns[1].get_text().strip()
            country = columns[3].get_text().strip().lower()
            version = columns[4].get_text().strip().lower()
            status = columns[5].get_text().strip().lower()

            if status == 'transparent':
                continue

            if not self.validate_country(country):
                continue

            if version == 'socks4' or version == 'socks5':
                proxy_url = '{}://{}:{}'.format(version, ip, port)
            else:
                proxy_url = '{}:{}'.format(ip, port)

            proxylist.append(proxy_url)

        if self.debug and not proxylist == 0:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist
