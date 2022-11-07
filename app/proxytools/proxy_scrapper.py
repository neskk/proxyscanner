#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests

from abc import ABC, abstractmethod
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from .config import Config
from .user_agent import UserAgent
from .utils import export_file, http_headers

log = logging.getLogger(__name__)


class ProxyScrapper(ABC):

    STATUS_FORCELIST = [500, 502, 503, 504]

    def __init__(self, name):
        super().__init__()
        args = Config.get_args()

        self.timeout = args.scrapper_timeout
        self.proxy = args.scrapper_proxy
        self.ignore_country = args.proxy_ignore_country
        self.debug = args.verbose
        self.download_path = args.download_path

        self.name = name
        self.user_agent = UserAgent.generate(args.user_agent)
        self.session = None
        self.retries = Retry(
            total=args.scrapper_retries,
            backoff_factor=args.scrapper_backoff_factor,
            status_forcelist=self.STATUS_FORCELIST)

        log.info('Initialized proxy scrapper: %s.', name)

    def setup_session(self):
        self.session = requests.Session()
        # Mount handler on both HTTP & HTTPS.
        self.session.mount('http://', HTTPAdapter(max_retries=self.retries))
        self.session.mount('https://', HTTPAdapter(max_retries=self.retries))

        self.session.proxies = {'http': self.proxy, 'https': self.proxy}

    def request_url(self, url, referer=None, post={}, json=False):
        content = None
        try:
            # Setup request headers.
            headers = http_headers(keep_alive=True)
            headers['user_agent'] = self.user_agent
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
            log.exception('Failed to request URL "%s": %s', url, e)

        return content

    def download_file(self, url, filename, referer=None):
        result = False
        try:
            # Setup request headers.
            headers = http_headers(keep_alive=True)
            headers['user_agent'] = self.user_agent
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

    @abstractmethod
    def scrap(self) -> list:
        """
        Scrap web content for valuable proxies.
        Returns:
            list: proxy list in url string format
        """
        pass
