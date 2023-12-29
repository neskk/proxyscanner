#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
from datetime import datetime
from timeit import default_timer as timer
from threading import Thread

from abc import ABC, abstractmethod
from urllib3.util.retry import Retry
from urllib3.exceptions import MaxRetryError
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, HTTPError

from .config import Config
from .db import DatabaseQueue
from .models import Proxy, ProxyProtocol, ProxyStatus, ProxyTest
from .user_agent import UserAgent
from .utils import export_file, http_headers, validate_ip, time_func

log = logging.getLogger(__name__)


class ProxyScrapper(ABC, Thread):

    STATUS_FORCELIST = [413, 429, 500, 502, 503, 504]

    def __init__(self, name, protocol=None):
        ABC.__init__(self)
        Thread.__init__(self, name=name, daemon=False)
        args = Config.get_args()
        self.args = args
        self.db_queue = DatabaseQueue.get_db_queue()

        self.timeout = args.scrapper_timeout
        self.proxy = None
        self.proxy_url = args.scrapper_proxy
        self.ignore_country = args.proxy_ignore_country
        self.debug = args.verbose
        self.download_path = args.download_path

        self.name = name
        self.protocol = protocol
        self.user_agent = UserAgent.generate(args.user_agent)
        self.session = None
        self.retries = Retry(
            allowed_methods=None,  # retry on all HTTP verbs
            total=args.scrapper_retries,
            backoff_factor=args.scrapper_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

        log.info('Initialized proxy scrapper: %s.', name)

    def get_protocol(self):
        return self.protocol

    def get_proxy(self):
        try:
            Proxy.database().connect()
            # proxy = Proxy.get_valid(limit=1).get()
            proxy = Proxy.get_random(limit=1).get()
            if proxy:
                self.proxy = proxy
                self.proxy_url = self.proxy.url()
        except Exception as e:
            log.error(f'Failed to get a valid proxy: {e}')
        finally:
            Proxy.database().close()

    def update_proxy(self, error=None):
        self.proxy.test_count += 1
        self.proxy.modified = datetime.utcnow()

        if error:
            self.proxy.fail_count += 1
            self.db_queue.update_proxy(self.proxy)
            self.db_queue.update_proxytest(ProxyTest(
                proxy=self.proxy,
                info=f'Failed to scrap webpage: {error}',
                status=ProxyStatus.ERROR))
        else:
            self.db_queue.update_proxy(self.proxy)
            self.db_queue.update_proxytest(ProxyTest(
                proxy=self.proxy,
                info='Scrapped webpage',
                status=ProxyStatus.OK))

    def setup_session(self):
        self.session = requests.Session()
        # Mount handler on both HTTP & HTTPS
        adapter = HTTPAdapter(max_retries=self.retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def setup_proxy(self, no_proxy=False):
        if no_proxy:
            self.proxy = None
            self.proxy_url = None
        elif self.args.scrapper_proxy:
            self.proxy = None
            self.proxy_url = self.args.scrapper_proxy
        elif not self.args.scrapper_anonymous:
            self.proxy = None
            self.proxy_url = None
        else:
            self.get_proxy()

        if self.proxy_url:
            self.timeout = self.args.scrapper_timeout * 3
        else:
            self.timeout = self.args.scrapper_timeout

        self.session.proxies = {'http': self.proxy_url, 'https': self.proxy_url}

    def make_request(self, url, referer=None, post={}, json=False):
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

        log.debug(f'Request history: {response.raw.retries.history}')
        response.raise_for_status()

        if json:
            content = response.json()
        else:
            content = response.text

        response.close()
        return content

    @time_func
    def request_url(self, url, referer=None, post={}, json=False):
        error_count = 0
        no_proxy = False
        while True:
            if self.db_queue.interrupt.is_set():
                break

            if error_count > 4:
                log.error('Unable to scrap proxies.')
                break
            start_t = timer()
            try:
                if error_count == 4:
                    continue  # XXX
                    log.debug('Not using proxy for next request.')
                    no_proxy = True
                self.setup_proxy(no_proxy)
                content = self.make_request(url, referer, post, json)
                if not content:
                    error_count += 1
                    continue

                if self.proxy:
                    self.update_proxy()

                return content
            except MaxRetryError as e:
                log.error(f'MaxRetryError: {e.reason}')
            except ConnectionError as e:
                log.error(f'Connection error: {e}')
            except HTTPError as e:
                log.error(f'HTTP error: {e}')
            except Exception as e:
                log.exception('Failed to request URL "%s": %s', url, e)

            log.debug(f'Request took: {timer()-start_t}')

            if self.proxy:
                self.update_proxy(error='connection error')

            error_count += 1

        return None

    def download_file(self, url, filename, referer=None):
        result = False
        try:
            raise RuntimeError('testing')
            # Setup request headers
            headers = http_headers(keep_alive=True)
            headers['User-Agent'] = self.user_agent
            headers['Referer'] = referer or 'https://www.google.com'

            response = self.session.get(
                url,
                # proxies={'http': self.proxy, 'https': self.proxy},
                timeout=self.timeout,
                headers=headers)

            response.raise_for_status()

            with open(filename, 'wb') as fd:
                for chunk in response.iter_content(chunk_size=128):
                    fd.write(chunk)
                result = True

            response.close()
        except Exception as e:
            log.exception('Failed to download file "%s": %s.', url, e)

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
            self.db_queue.insert_proxylist(proxylist)

        except Exception as e:
            log.exception(f'{self.name} proxy scrapper failed: {e}')

    @abstractmethod
    def scrap(self) -> list:
        """
        Scrap web content for valuable proxies.
        Returns:
            list: proxy list in url string format
        """
        pass
