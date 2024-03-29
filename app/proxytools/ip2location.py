#!/usr/bin/python
# -*- coding: utf-8 -*-

import IP2Location
import logging
import os
import requests
import time

from threading import Lock
from zipfile import ZipFile, is_zipfile

log = logging.getLogger(__name__)


class IP2LocationDatabase(object):
    URL = 'https://download.ip2location.com/lite/IP2LOCATION-LITE-DB1.BIN.ZIP'
    DATABASE_FILE = 'IP2LOCATION-LITE-DB1.BIN'
    DATABASE_ZIP = 'IP2LOCATION-LITE-DB1.BIN.ZIP'

    def __init__(self, args):
        self.lock = Lock()
        self.download_path = args.download_path

        database_file = os.path.join(args.download_path, self.DATABASE_FILE)

        if not os.path.isfile(database_file):
            log.debug('IP2Location database not found, downloading...')
            self.__download_database()
        else:
            mtime = os.path.getmtime(database_file)
            if time.time() > mtime + (30 * 24 * 3600):
                log.debug('IP2Location database is 1+ month old, downloading update...')
                self.__download_database()

        self.database = IP2Location.IP2Location(database_file)
        log.debug('IP2Location Lite DB1 initialized.')

    def __download_database(self):
        download_file = os.path.join(self.download_path, self.DATABASE_ZIP)
        result = False

        try:
            response = requests.get(self.URL)
            with open(download_file, 'wb') as fd:
                for chunk in response.iter_content(chunk_size=128):
                    fd.write(chunk)
            response.close()

            if not is_zipfile(download_file):
                log.error('File "%s" downloaded from %s is not a Zip archive.',
                          download_file, self.URL)
            else:
                with ZipFile(download_file, 'r') as myzip:
                    for filename in myzip.namelist():
                        if filename.endswith(self.DATABASE_FILE):
                            myzip.extract(filename, self.download_path)
                            result = True
                            break
        except Exception as e:
            log.exception('Unable to download IP2Location Lite DB1: %s', e)

        return result

    def lookup_country(self, ip: str) -> str:
        """
        Find country name associated with an IP address.

        Args:
            ip (str): IP address

        Returns:
            str: ISO 3166-1 alpha-2 code
        """
        self.lock.acquire()
        try:
            row = self.database.get_all(ip)
            return row.country_short.lower()
        except Exception as e:
            log.warning(f'Unable to lookup country for "{ip}": {e}')
        finally:
            self.lock.release()
