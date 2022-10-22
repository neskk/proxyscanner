#!/usr/bin/python
# -*- coding: utf-8 -*-

from proxytools.crazyxor import parse_crazyxor, decode_crazyxor
from bs4 import BeautifulSoup
import re
import requests


# base_url = 'https://free-proxy-list.net'
# response = requests.get(base_url)
# html = response.content

html = None
with open('downloads/http _spys.one_en_https-ssl-proxy_.html', 'r') as fd:
    html = fd.read()

soup = BeautifulSoup(html, 'html.parser')
encoding = {}
for script in soup.find_all('script'):
    code = script.get_text()
    for line in code.split('\n'):
        if '^' in line and ';' in line and '=' in line:
            line = line.strip()
            print('Found crazy XOR decoding secret code.')
            encoding = parse_crazyxor(line)

for key, value in encoding.iteritems():
    print(key + ' : ' + value)

for row in soup.find_all('tr', attrs={'class': ['spy1x', 'spy1xx']}):
    columns = row.find_all('td')
    if len(columns) != 10:
        print('Bad table row selected, ignoring...')
        continue

    fonts = columns[0].find_all('font')

    if len(fonts) != 2:
        print('Bad format...')
        continue

    info = fonts[1]
    obfuscated = info.find('script').extract()
    script = obfuscated.get_text()

    ip = info.get_text()
    print(ip)

    matches = re.findall('\(([\w\^]+)\)', script)
    port = ''.join([decode_crazyxor(encoding, match) for match in matches])

    print(port)
    country = columns[3].get_text()
    country = re.match('([\w\s]+) \(.*', country)

    if country:
        country = country.group(1).lower()
        print(country)