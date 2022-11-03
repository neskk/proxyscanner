#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from .config import Config
from .utils import validate_ip
from .models import ProxyProtocol, Proxy

from .scrappers.filereader import FileReader
from .scrappers.freeproxylist import Freeproxylist
from .scrappers.premproxy import Premproxy
from .scrappers.socksproxy import Socksproxy
from .scrappers.spysone import SpysHTTPS, SpysSOCKS
from .scrappers.openproxy import OpenProxyHTTP, OpenProxySOCKS4, OpenProxySOCKS5
from .scrappers.proxyscrape import ProxyScrapeHTTP, ProxyScrapeSOCKS4, ProxyScrapeSOCKS5
from .scrappers.thespeedx import TheSpeedXHTTP, TheSpeedXSOCKS4, TheSpeedXSOCKS5
from .scrappers.geonode import GeoNodeHTTP, GeoNodeSOCKS4, GeoNodeSOCKS5
# from .scrappers.idcloak import Idcloak
# from .scrappers.proxyserverlist24 import Proxyserverlist24
# from .scrappers.sockslist import Sockslist
# from .scrappers.socksproxylist24 import Socksproxylist24
# from .scrappers.vipsocks24 import Vipsocks24

from .scrappers.proxynova import ProxyNova

log = logging.getLogger(__name__)


class ProxyParser(object):

    def __init__(self, protocol=None):
        self.args = Config.get_args()

        args = self.args
        self.debug = args.verbose
        self.download_path = args.download_path
        self.refresh_interval = args.proxy_refresh_interval
        self.protocol = protocol

        # Configure proxy scrappers.
        self.scrappers = []

    def __parse_proxylist(self, proxylist):
        result = []

        for proxy in proxylist:
            # Strip spaces from proxy string.
            proxy = proxy.strip()
            if len(proxy) < 9:
                log.debug('Invalid proxy address: %s', proxy)
                continue

            parsed = {
                'ip': None,
                'port': None,
                'protocol': self.protocol,
                'username': None,
                'password': None
            }

            # Check and separate protocol from proxy address.
            if '://' in proxy:
                pieces = proxy.split('://')
                proxy = pieces[1]
                if pieces[0] == 'http':
                    parsed['protocol'] = ProxyProtocol.HTTP
                elif pieces[0] == 'socks4':
                    parsed['protocol'] = ProxyProtocol.SOCKS4
                elif pieces[0] == 'socks5':
                    parsed['protocol'] = ProxyProtocol.SOCKS5
                else:
                    log.error('Unknown proxy protocol in: %s', proxy)
                    continue

            if parsed['protocol'] is None:
                log.error('Proxy protocol is not set for: %s', proxy)
                continue

            # Check and separate authentication from proxy address.
            if '@' in proxy:
                pieces = proxy.split('@')
                if ':' not in pieces[0]:
                    log.error('Unknown authentication format in: %s', proxy)
                    continue
                auth = pieces[0].split(':')

                parsed['username'] = auth[0]
                parsed['password'] = auth[1]
                proxy = pieces[1]

            # Check and separate IP and port from proxy address.
            if ':' not in proxy:
                log.error('Proxy address port not specified in: %s', proxy)
                continue

            pieces = proxy.split(':')

            if not validate_ip(pieces[0]):
                log.error('IP address is not valid in: %s', proxy)
                continue

            parsed['ip'] = pieces[0]
            parsed['port'] = pieces[1]

            result.append(parsed)

        log.info('Successfully parsed %d proxies.', len(result))
        return result

    def load_proxylist(self):
        if not self.scrappers:
            return

        proxylist = set()

        for scrapper in self.scrappers:
            try:
                proxylist.update(scrapper.scrap())
            except Exception as e:
                log.exception('%s proxy scrapper failed: %s',
                              type(scrapper).__name__, e)

        log.info('%s scrapped a total of %d proxies.',
                 type(self).__name__, len(proxylist))
        proxylist = self.__parse_proxylist(proxylist)
        Proxy.insert_bulk(proxylist)


class MixedParser(ProxyParser):

    def __init__(self):
        super(MixedParser, self).__init__()
        if self.args.proxy_file:
            self.scrappers.append(FileReader())


class HTTPParser(ProxyParser):

    def __init__(self):
        super(HTTPParser, self).__init__(ProxyProtocol.HTTP)
        if not self.args.proxy_scrap:
            return

        self.scrappers.append(Freeproxylist())
        self.scrappers.append(Premproxy())
        self.scrappers.append(SpysHTTPS())  # SpyOne
        self.scrappers.append(ProxyNova())
        self.scrappers.append(OpenProxyHTTP())
        self.scrappers.append(ProxyScrapeHTTP())
        self.scrappers.append(TheSpeedXHTTP())
        self.scrappers.append(GeoNodeHTTP())


class SOCKS4Parser(ProxyParser):

    def __init__(self):
        super(SOCKS4Parser, self).__init__(ProxyProtocol.SOCKS4)
        if not self.args.proxy_scrap:
            return

        self.scrappers.append(OpenProxySOCKS4())
        self.scrappers.append(ProxyScrapeSOCKS4())
        self.scrappers.append(TheSpeedXSOCKS4())
        self.scrappers.append(GeoNodeSOCKS4())


class SOCKS5Parser(ProxyParser):

    def __init__(self):
        super(SOCKS5Parser, self).__init__(ProxyProtocol.SOCKS5)
        if not self.args.proxy_scrap:
            return

        self.scrappers.append(Socksproxy())
        self.scrappers.append(SpysSOCKS())  # SpyOne
        self.scrappers.append(OpenProxySOCKS5())
        self.scrappers.append(ProxyScrapeSOCKS5())
        self.scrappers.append(TheSpeedXSOCKS5())
        self.scrappers.append(GeoNodeSOCKS5())
