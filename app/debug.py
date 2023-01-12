#!/usr/bin/python
# -*- coding: utf-8 -*-
# flake8: noqa:F401

import logging
from pprint import pprint
import math
import random
import time

from datetime import datetime, timedelta
from functools import wraps
from timeit import default_timer as timer

from proxytools.app import App
from proxytools.config import Config
from proxytools.utils import configure_logging, random_ip

from proxytools.models import Proxy, ProxyTest, ProxyProtocol, ProxyStatus

log = logging.getLogger()


def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        log.info(f'Function {func.__name__}{args} {kwargs} Took {total_time:.3f} seconds')
        return result
    return timeit_wrapper


@timeit
def add_proxies(amount=1):
    data = []
    protocols = list(map(int, ProxyProtocol))
    for i in range(amount):
        port = random.randint(80, 9000)
        data.append({
            'ip': random_ip(),
            'port': port,
            'protocol': random.choices(protocols)[0]
        })

    q = Proxy.insert_bulk(data)
    return q


@timeit
def add_proxytests(proxy_id, amount=3, only_valid=False):
    data = []

    if only_valid:
        statuses = [ProxyStatus.OK]
    else:
        statuses = list(map(int, ProxyStatus))

    for i in range(amount):
        data.append({
            'proxy_id': proxy_id,
            'latency': random.randint(50, 5000),
            'status': random.choices(statuses)[0]
        })

    q = ProxyTest.insert_many(data)
    return q.execute()


def populate_proxies(proxy_count=1000):
    start_time = timer()
    db_proxy_count = Proxy.select().count()
    elapsed_time = timer() - start_time
    log.info(f'{db_proxy_count} proxies in the database. Query took: {elapsed_time:.3f}s')

    proxy_count -= db_proxy_count

    if proxy_count > 0:
        log.info(f'Inserting {proxy_count} proxies...')
        start_time = timer()
        add_proxies(proxy_count)
        elapsed_time = timer() - start_time
        log.info(f"Inserting {proxy_count} proxies took: {elapsed_time:.3f}s")


def populate_proxytests(testspp=5, only_valid=False):
    data = []

    if only_valid:
        statuses = [ProxyStatus.OK]
    else:
        statuses = list(map(int, ProxyStatus))

    db_proxy_count = Proxy.select().count()
    test_count = db_proxy_count/testspp
    q = Proxy.select(Proxy.id).dicts()

    for proxy_id in q:
        for i in range(test_count):
            data.append({
                'proxy_id': proxy_id,
                'latency': random.randint(50, 5000),
                'status': random.choices(statuses)[0]
            })

    q = ProxyTest.insert_many(data)
    return q.execute()


def populate_data(proxy_count=1000, test_count=250000):
    start_time = timer()
    db_proxy_count = Proxy.select().count()
    elapsed_time = timer() - start_time
    log.info(f'{db_proxy_count} proxies in the database. Query took: {elapsed_time:.3f}s')

    proxy_count -= db_proxy_count

    if proxy_count > 0:
        log.info(f'Inserting {proxy_count} proxies...')
        start_time = timer()
        add_proxies(proxy_count)
        elapsed_time = timer() - start_time
        log.info(f"Inserting {proxy_count} proxies took: {elapsed_time:.3f}s")

    start_time = timer()
    db_test_count = ProxyTest.select().count()
    elapsed_time = timer() - start_time
    log.info(f'{db_test_count} proxy tests in the database. Query took: {elapsed_time:.3f}s')
    test_count -= db_test_count

    if test_count > 0:
        # refresh number of existing proxies
        db_proxy_count = Proxy.select().count()
        testspp = math.ceil(test_count / db_proxy_count)

        log.info(f'Inserting {test_count} tests, {testspp} on each proxy...')
        start_time = timer()
        for proxy in Proxy.get_random(db_proxy_count).dicts():
            add_proxytests(proxy['id'], testspp, False)
        elapsed_time = timer() - start_time
        log.info(f'Inserting {test_count} tests took: {elapsed_time:.3f}s')


@timeit
def query_valid(limit=1000, output=False):
    q = Proxy.get_valid(limit)
    log.debug(q.sql())
    l = [m for m in q.dicts()]
    if output:
        pprint(l)


@timeit
def query_latest_test(proxy: Proxy):
    q = proxy.latest_test()
    pprint(q)


@timeit
def query_oldest_test(proxy: Proxy):
    q = proxy.oldest_test()
    pprint(q)


if __name__ == '__main__':
    args = Config.get_args()
    configure_logging(log, args.verbose, args.log_path, "-debug")

    app = App()

    # 2500000 tests should take about 20min to insert in the database.
    # populate_data(10000, 2500000)


    """
    proxies = [
        {
            'ip': '123.1.1.1',
            'port': '88',
            'protocol': ProxyProtocol.HTTP,
            #'tests': [ {'latency': 80, 'status': 0} ]
        },
        {
            'ip': '123.2.2.2',
            'port': '88',
            'protocol': ProxyProtocol.HTTP,
            #'tests': [ {'latency': 100, 'status': 0} ]
        },
        {
            'ip': '123.3.3.3',
            'port': '88',
            'protocol': ProxyProtocol.SOCKS4,
            'username': 'neskk',
            'password': 'test'
            #'tests': [ {'latency': 100, 'status': 0} ]
        },
    ]

    Proxy.insert_bulk(proxies)
    """

