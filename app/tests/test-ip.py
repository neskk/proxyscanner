#!/usr/bin/python
# -*- coding: utf-8 -*-

import socket
import struct


def ip2int(addr):
    return struct.unpack('!I', socket.inet_aton(addr))[0]


def int2ip(addr):
    return socket.inet_ntoa(struct.pack('!I', addr))


ip = '192.168.01.12'
ip_int = ip2int(ip)

# print(ip)
# print(str(ip_int))
# print(int2ip(ip_int))


def hash_proxy(proxy):
    return hash(
        (proxy['ip'], proxy['port'], proxy['username'], proxy['password']))


class ProxyDict(dict):
    def __hash__(self):
        return hash((self.get('ip'), self.get('port')))

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne_(self, other):
        return self.__hash__() != other.__hash__()


class ProxyDict2(dict):

    def __hash__(self):
        return hash((self.get('ip'), self.get('port')))

    def __eq__(self, other):
        return (isinstance(other, ProxyDict) and
                ((self.get('ip'), self.get('port')) ==
                 (other.get('ip'), other.get('port'))))

    def __ne_(self, other):
        return not(self == other)


# proxy = ProxyDict(ip_int, 8080, 'a')
# proxy2 = ProxyDict(ip_int, 8081, 'a')
# proxy3 = ProxyDict(ip_int, 8080, 'bbbb')

proxy = ProxyDict({
    'ip': ip_int,
    'port': 8080,
    'x': 'a'
})

proxy2 = ProxyDict({
    'ip': ip_int,
    'port': 8081,
    'x': 'a'
})

proxy3 = ProxyDict({
    'ip': ip_int,
    'port': 8080,
    'x': 'bbbbb'
})

dic = {
    'ip': ip_int,
    'port': 8080,
    'username': None,
    'password': None
}

dic2 = {
    'ip': ip_int,
    'port': 8080,
    'username': None,
    'password': None
}

dic3 = {
    'ip': ip_int,
    'port': 8080,
    'x': 'bbbbb'
}


print(hash_proxy(dic))
print(hash_proxy(dic2))
print(hash_proxy(dic2))

xxx = [proxy, proxy2]
dics = [dic, dic2, dic3]

if proxy3 in xxx:
    print('eureka!')

print(proxy3['ip'])

proxies = set()
dicts = {}

proxies.add(proxy)
dicts[proxy] = proxy

print(proxies)
# print(dicts)

proxies.add(proxy2)
dicts[proxy2] = proxy2

print(proxies)
# print(dicts)

proxies.add(proxy3)
dicts[proxy3] = proxy3

print(proxies)
# print(dicts)
