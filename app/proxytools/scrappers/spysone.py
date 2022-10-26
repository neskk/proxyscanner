#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
# import random
import re
# import time

from bs4 import BeautifulSoup

from ..crazyxor import parse_crazyxor, decode_crazyxor
from ..packer import deobfuscate
from ..proxy_scrapper import ProxyScrapper
from ..utils import validate_ip

log = logging.getLogger(__name__)


class SpysOne(ProxyScrapper):

    def __init__(self, name):
        super(SpysOne, self).__init__(name)

    def scrap(self):
        self.setup_session()
        proxylist = []

        url = self.base_url

        html = self.request_url(url, url)
        if not html:
            return proxylist
        param = self.parse_secret(html)
        log.debug('Found secret "xx0" parameter: %s', param)

        post_data = f'xx0={param}&{self.post_data}'
        log.debug('POST data being sent: %s', post_data)
        html = self.request_url(url, url, post=post_data)
        if html is None:
            log.error('Failed to download webpage: %s', url)
        else:
            log.info('Parsing proxylist from webpage: %s', url)
            proxylist.extend(self.parse_webpage(html))
            # time.sleep(random.uniform(2.0, 4.0))

        self.session.close()
        return proxylist

    def parse_secret(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        secret = soup.find('input', attrs={'type': 'hidden', 'name': 'xx0'})
        if not secret:
            log.error('Unable to find secret "xx0" parameter.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return None

        return secret.get('value')

    def parse_webpage(self, html):
        proxylist = []
        encoding = {}
        soup = BeautifulSoup(html, 'html.parser')

        for script in soup.find_all('script'):

            code = script.string
            if not code:
                continue

            for line in code.split('\n'):
                if '^' in line and ';' in line and '=' in line:
                    line = line.strip()
                    log.info('Found crazy XOR decoding script.')
                    # log.debug("Script: %s" % line)
                    clean_code = deobfuscate(line)
                    if clean_code:
                        line = clean_code
                        # log.debug("Unpacked script: %s" % clean_code)
                    # Check to see if script contains the decoding function.
                    encoding = parse_crazyxor(line)
                    log.debug('Crazy XOR decoding dictionary: %s', encoding)

        if not encoding:
            log.error('Unable to find crazy XOR decoding script.')

            if self.debug:
                self.export_webpage(soup, self.name + '.html')

            return proxylist

        # Select table rows and skip first one.
        table_rows = soup.find_all('tr', attrs={'class': ['spy1x', 'spy1xx']})[1:]

        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) != 10:
                # Bad table row selected, moving on.
                continue

            # Format:
            #   <td colspan="1">
            #     <font class="spy14">
            #         183.88.16.161
            #         <script type="text/javascript">
            #         document.write("<font class=spy2>:<\/font>"+(x4w3y5^x4o5)+(m3n4d4^a1c3)+(i9a1c3^g7r8)+(i9a1c3^g7r8)+(k1g7w3^p6s9))
            #         </script>
            #     </font>
            #   </td>

            # Grab first column
            fonts = columns[0].find_all('font')
            if len(fonts) != 1:
                log.warning('Unknown format of proxy table cell.')
                continue

            info = fonts[0]
            script = info.find('script')

            if not script:
                log.warning('Unable to find port obfuscation script.')
                continue

            # Remove script tag from contents.
            script = script.extract().string
            if not script:
                continue

            ip = info.get_text()

            if not validate_ip(ip):
                log.warning('Invalid IP found: %s', ip)
                continue

            matches = re.findall(r'\(([\w\d\^]+)\)', script)
            numbers = [decode_crazyxor(encoding, m) for m in matches]
            port = ''.join(numbers)

            anonymous = columns[2].get_text()
            if anonymous != 'ANM' and anonymous != 'HIA':
                log.debug('Skipped non-anonymous proxy.')
                continue

            country = columns[3].get_text().lower()
            clean_name = re.match('([\w\s]+) \(.*', country)

            if clean_name:
                country = clean_name.group(1)

            if not self.validate_country(country):
                continue

            proxy_url = '{}:{}'.format(ip, port)
            proxylist.append(proxy_url)

        if self.debug and not proxylist:
            self.export_webpage(soup, self.name + '.html')

        log.info('Parsed %d proxies from webpage.', len(proxylist))
        return proxylist


class SpysHTTPS(SpysOne):

    def __init__(self):
        super(SpysHTTPS, self).__init__('spys-one-https')
        self.base_url = 'https://spys.one/en/https-ssl-proxy/'
        self.post_data = 'xpp=5&xf1=1&xf4=0&xf5=0'


class SpysSOCKS(SpysOne):

    def __init__(self):
        super(SpysSOCKS, self).__init__('spys-one-socks')
        self.base_url = 'https://spys.one/en/socks-proxy-list/'
        self.post_data = 'xpp=5&xf1=0&xf2=0&xf4=0&xf5=0'
