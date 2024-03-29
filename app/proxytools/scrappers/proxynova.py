#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

from bs4 import BeautifulSoup

from ..deobfuscate_js import deobfuscate_js
from ..models import ProxyProtocol
from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


class ProxyNova(ProxyScrapper):

    def __init__(self):
        super(ProxyNova, self).__init__('proxynova-com', ProxyProtocol.HTTP)
        self.base_url = 'https://www.proxynova.com'
        self.urls = (
            'https://www.proxynova.com/proxy-server-list/elite-proxies/',
            'https://www.proxynova.com/proxy-server-list/anonymous-proxies/'
        )

    def scrap(self):
        self.setup_session()
        proxylist = []

        for url in self.urls:
            html = self.request_url(url, self.base_url)
            if html is None:
                log.error('Failed to download webpage: %s', url)
                continue

            log.info('Parsing proxylist from webpage: %s', url)
            proxies = self.parse_webpage(html)
            proxylist.extend(proxies)

        self.session.close()
        return proxylist

    def parse_webpage(self, html):
        proxylist = []
        soup = BeautifulSoup(html, 'html.parser')

        table = soup.find('table', attrs={'id': 'tbl_proxy_list'})
        tbody = table.find('tbody')

        if not tbody:
            log.error('Unable to find proxylist table.')
            return proxylist

        table_rows = tbody.find_all('tr')
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 7:
                continue

            # several obfuscation methods being used on rotation
            ip_script = columns[0].find('script').string
            m = re.search(r"document.write\((.*)\)$", ip_script)

            if not m:
                log.error('Invalid IP format on IP column.')
                break

            ip = None
            try:
                ip = deobfuscate_js(m.group(1))
            except Exception:
                log.exception('Unable to deobfuscate IP from: %s', m.group(1))
                continue

            if not ip or not validate_ip(ip):
                log.error('Invalid IP format parsed.')
                continue

            port = columns[1].get_text().strip()
            country = columns[5].find('a')
            city = country.find('span')
            if city:
                # remove city from country cell
                city = city.extract()

            country = country.get_text().strip().lower()
            status = columns[6].find('span').get_text().strip().lower()

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
