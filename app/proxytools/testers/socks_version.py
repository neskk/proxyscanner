#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import socket
import struct

from timeit import default_timer as timer

from ..models import Proxy, ProxyProtocol, ProxyStatus, ProxyTest
from ..test import Test

log = logging.getLogger(__name__)


class SOCKSVersion(Test):

    def __test_socks4(self, host, port, soc):
        ipaddr = socket.inet_aton(host)
        port_pack = struct.pack(">H", port)
        packet4 = b"\x04\x01" + port_pack + ipaddr + b"\x00"
        soc.sendall(packet4)
        data = soc.recv(8)
        if len(data) < 2:
            # Null response
            return False
        if data[0] != int("0x00", 16):
            # Bad data
            return False
        if data[1] != int("0x5A", 16):
            # Server returned an error
            return False
        return True

    def __test_socks5(self, host, port, soc):
        soc.sendall(b"\x05\x01\x00")
        data = soc.recv(2)
        if len(data) < 2:
            # Null response
            return False
        if data[0] != int("0x05", 16):
            # Not socks5
            return False
        if data[1] != int("0x00", 16):
            # Requires authentication
            return False
        return True

    def __init__(self, manager):
        super().__init__(manager)

    def __skip_test(self, proxy: Proxy) -> bool:
        if proxy.protocol == ProxyProtocol.HTTP:
            return True
        return False

    def validate(self):
        return True

    def run(self, proxy: Proxy) -> ProxyTest:
        """
        Check SOCKS protocol version using a socket.

        Args:
            proxy (Proxy): proxy being tested

        Returns:
            ProxyTest: test results
        """
        proxy_url = proxy.url()

        if self.__skip_test(proxy):
            log.debug('Skipped SOCKS version test for proxy: %s', proxy_url)
            return None

        proxy_test = ProxyTest(proxy=proxy, info="SOCKS version test")

        start_time = timer()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.args.tester_timeout)
        try:
            s.connect((proxy.ip, proxy.port))
            if self.__test_socks4(proxy.ip, proxy.port, s):
                proxy.protocol = ProxyProtocol.SOCKS4
            elif self.__test_socks5(proxy.ip, proxy.port, s):
                proxy.protocol = ProxyProtocol.SOCKS5
            else:
                proxy_test.status = ProxyStatus.ERROR
                proxy_test.info = 'SOCKS not supported'

                proxy.protocol = ProxyProtocol.HTTP
                log.info('Changed proxy %s to HTTP proxy.')

        except socket.timeout:
            proxy_test.status = ProxyStatus.TIMEOUT
            proxy_test.info = 'Connection timed out'

        except socket.error as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Connection refused - ' + type(e).__name__
        except Exception as e:
            proxy_test.status = ProxyStatus.ERROR
            proxy_test.info = 'Unexpected error - ' + type(e).__name__
            log.exception('Unexpected error: %s', e)
        finally:
            s.close()

        proxy_test.latency = int((timer() - start_time) * 1000)

        # Save test results
        self.save(proxy_test)

        return proxy_test
