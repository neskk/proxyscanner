#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
from threading import Thread
import time
import requests

from abc import ABC, abstractmethod
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from peewee import DatabaseError
from playhouse.pool import MaxConnectionsExceeded

from .config import Config
from .models import Proxy, ProxyProtocol
from .user_agent import UserAgent
from .utils import export_file, http_headers, validate_ip

log = logging.getLogger(__name__)


class ProxyScrapper(ABC, Thread):

    STATUS_FORCELIST = [500, 502, 503, 504]

    def __init__(self, name, protocol=None):
        ABC.__init__(self)
        Thread.__init__(self, name=name, daemon=False)
        args = Config.get_args()
        self.args = args

        self.timeout = args.scrapper_timeout
        self.proxy = args.scrapper_proxy
        self.ignore_country = args.proxy_ignore_country
        self.debug = args.verbose
        self.download_path = args.download_path

        self.name = name
        self.protocol = protocol
        self.user_agent = UserAgent.generate(args.user_agent)
        self.session = None
        self.retries = Retry(
            total=args.scrapper_retries,
            backoff_factor=args.scrapper_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

        log.info('Initialized proxy scrapper: %s.', name)

    def get_protocol(self):
        return self.protocol

    def setup_session(self):
        self.session = requests.Session()
        # Mount handler on both HTTP & HTTPS
        self.session.mount('http://', HTTPAdapter(max_retries=self.retries))
        self.session.mount('https://', HTTPAdapter(max_retries=self.retries))

        self.session.proxies = {'http': self.proxy, 'https': self.proxy}

    def request_url(self, url, referer=None, post={}, json=False):
        content = None
        try:
            # Setup request headers
            headers = http_headers()
            headers['User-Agent'] = self.user_agent
            headers['Referer'] = referer or 'https://www.google.com'

            if post:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                response = self.session.post(
                    url,
                    timeout=self.timeout,
                    headers=headers,
                    data=post)
            else:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    headers=headers)

            response.raise_for_status()

            if json:
                content = response.json()
            else:
                content = response.text

            response.close()
        except Exception as e:
            log.error('Failed to request URL "%s": %s', url, e)

        return content

    def download_file(self, url, filename, referer=None):
        result = False
        try:
            # Setup request headers
            headers = http_headers(keep_alive=True)
            headers['User-Agent'] = self.user_agent
            headers['Referer'] = referer or 'https://www.google.com'

            response = self.session.get(
                url,
                proxies={'http': self.proxy, 'https': self.proxy},
                timeout=self.timeout,
                headers=headers)

            response.raise_for_status()

            with open(filename, 'wb') as fd:
                for chunk in response.iter_content(chunk_size=128):
                    fd.write(chunk)
                result = True

            response.close()
        except Exception as e:
            log.error('Failed to download file "%s": %s.', url, e)

        return result

    def export_webpage(self, soup, filename):
        content = soup.prettify()  # .encode('utf8')
        filename = '{}/{}'.format(self.download_path, filename)

        export_file(filename, content)
        log.debug('Web page output saved to: %s', filename)

    def validate_country(self, country):
        valid = True
        for ignore_country in self.ignore_country:
            if ignore_country in country:
                valid = False
                break
        return valid

    def parse_proxy(self, line: str) -> dict:
        proxy = {
            'ip': None,
            'port': None,
            'protocol': self.protocol,
            'username': None,
            'password': None
        }

        # Check and separate protocol from proxy address
        if '://' in line:
            pieces = line.split('://')
            line = pieces[1]
            if pieces[0] == 'http':
                proxy['protocol'] = ProxyProtocol.HTTP
            elif pieces[0] == 'socks4':
                proxy['protocol'] = ProxyProtocol.SOCKS4
            elif pieces[0] == 'socks5':
                proxy['protocol'] = ProxyProtocol.SOCKS5
            else:
                raise ValueError(f'Unknown proxy protocol in: {line}')

        if proxy['protocol'] is None:
            raise ValueError(f'Proxy protocol is not set for: {line}')

        # Check and separate authentication from proxy address
        if '@' in line:
            pieces = line.split('@')
            if ':' not in pieces[0]:
                raise ValueError(f'Unknown authentication format in: {line}')
            auth = pieces[0].split(':')

            proxy['username'] = auth[0]
            proxy['password'] = auth[1]
            line = pieces[1]

        # Check and separate IP and port from proxy address
        if ':' not in line:
            raise ValueError(f'Proxy address port not specified in: {line}')

        pieces = line.split(':')

        if not validate_ip(pieces[0]):
            raise ValueError(f'IP address is not valid in: {line}')

        proxy['ip'] = pieces[0]
        proxy['port'] = pieces[1]

        return proxy

    def parse_proxylist(self, proxylist: list) -> list:
        """
        Parse proxy URL strings into dictionaries with model attributes.

        Args:
            proxylist (list): list of proxy URL strings to parse

        Returns:
            list: Proxy model dictionaries
        """
        result = []

        for line in proxylist:
            line = line.strip()
            if len(line) < 9:
                log.debug('Invalid proxy address: %s', line)
                continue
            try:
                proxy_dict = self.parse_proxy(line)
                result.append(proxy_dict)
            except ValueError as e:
                log.error(e)

        log.info('%s successfully parsed %d proxies.', self.name, len(result))
        return result

    def run(self):
        try:
            proxylist = self.scrap()
            log.info('%s scrapped a total of %d proxies.', self.name, len(proxylist))
            proxylist = self.parse_proxylist(proxylist)
            for i in range(5):
                if self.update_database(proxylist):
                    break
                time.sleep(3.0)

        except Exception as e:
            log.exception(f'{self.name} proxy scrapper failed: {e}')

    def update_database(self, proxylist):
        try:
            Proxy.database().connect()
            Proxy.insert_bulk(proxylist)
            return True
        except DatabaseError as e:
            log.critical(f'Failed to insert scrapped proxies: {e}')
        except MaxConnectionsExceeded as e:
            log.critical(
                f'Unable to insert scrapped proxies: {e}\n'
                'Increase max DB connections or decrease # of threads!')
        finally:
            Proxy.database().close()

        return False

    @abstractmethod
    def scrap(self) -> list:
        """
        Scrap web content for valuable proxies.
        Returns:
            list: proxy list in url string format
        """
        pass
