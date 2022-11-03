#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import math

from ..proxy_scrapper import ProxyScrapper
from ..utils import load_file

log = logging.getLogger(__name__)

# https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps&anonymityLevel=elite&anonymityLevel=anonymous
# https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks4&anonymityLevel=elite&anonymityLevel=anonymous
# https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks5&anonymityLevel=elite&anonymityLevel=anonymous


class GeoNode(ProxyScrapper):
    def __init__(self, name):
        super(GeoNode, self).__init__(name)
        self.base_url = ('https://proxylist.geonode.com/api/proxy-list'
                         '?limit=500&sort_by=lastChecked&sort_type=desc'
                         '&anonymityLevel=elite&anonymityLevel=anonymous')

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
        proxylist = []

        page = 1
        total_pages = 1

        while page <= total_pages:
            url = self.base_url + f'&page={page}'
            json = self.request_url(url, json=True)

            if json is None:
                log.error('Failed to download webpage: %s', url)
                return proxylist

            if page == 1:
                total_pages = math.ceil(json['total'] / json['limit'])

            page += 1

            log.info('Parsing proxylist from webpage: %s', url)
            for row in json.get('data', []):
                proxylist.append(f'{row["ip"]}:{row["port"]}')

        self.session.close()
        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist


class GeoNodeHTTP(GeoNode):

    def __init__(self):
        super(GeoNodeHTTP, self).__init__('geo-node-http')
        self.base_url += '&protocols=http%2Chttps'


class GeoNodeSOCKS4(GeoNode):

    def __init__(self):
        super(GeoNodeSOCKS4, self).__init__('geo-node-socks4')
        self.base_url += '&protocols=socks4'


class GeoNodeSOCKS5(GeoNode):

    def __init__(self):
        super(GeoNodeSOCKS5, self).__init__('geo-node-socks5')
        self.base_url += '&protocols=socks5'
