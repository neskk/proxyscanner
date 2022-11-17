#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from bs4 import BeautifulSoup

from ..models import ProxyProtocol
from ..proxy_scrapper import ProxyScrapper

log = logging.getLogger(__name__)


class Freeproxylist(ProxyScrapper):

    def __init__(self):
        super(Freeproxylist, self).__init__('freeproxylist-net', ProxyProtocol.HTTP)
        self.base_url = 'https://free-proxy-list.net'

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
            status = columns[4].get_text().strip().lower()

            if not self.validate_country(country):
                continue

            if status == 'transparent':
                continue

            proxy_url = '{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d http proxies from webpage.', len(proxylist))
        return proxylist
