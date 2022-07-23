#!/usr/bin/python
# -*- coding: utf-8 -*-
# py -3 -m app.tests.test-freeproxylist

from bs4 import BeautifulSoup
import os
import re
import requests
import sys

from ..proxytools import utils
from ..proxytools.config import Config
from ..proxytools.scrappers.freeproxylist import Freeproxylist
from ..proxytools.crazyxor import parse_crazyxor, decode_crazyxor


# base_url = 'https://free-proxy-list.net'
# response = requests.get(base_url)
# html = response.content

args = Config.get_args()
scrapper = Freeproxylist(args)

filename = '{}/{}.html'.format(args.download_path, scrapper.name)
html = None
if os.path.exists(filename):
    with open(filename, 'r') as f:
        html = f.read()
else:
    scrapper.setup_session()
    html = scrapper.request_url(scrapper.base_url)
    scrapper.session.close()

    if html is None:
        print(f"Failed to download webpage: {scrapper.base_url}")
        sys.exit(1)
    else:
        utils.export_file(filename, html)

# Parse HTML
soup = BeautifulSoup(html, 'html.parser')

table = soup.select_one('div.fpl-list table')

print(table)