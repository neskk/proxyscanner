#!/usr/bin/python
# -*- coding: utf-8 -*-

from enum import Enum
from typing import Any
import configargparse
import pycountry
import os
import sys

from .models import ProxyProtocol
from .utils import find_local_ip

CWD = os.path.dirname(os.path.realpath(__file__))
APP_PATH = os.path.realpath(os.path.join(CWD, '..'))


class Config:
    """ Singleton class that parses and holds all the configuration arguments """
    __args = None
    __counter = 0

    @staticmethod
    def get_args():
        """ Static access method """
        if Config.__args is None:
            Config()
        return Config.__args

    @staticmethod
    def get_proxyjudge():
        """ Get and cycle proxy judges """
        if Config.__args is None:
            raise Exception('Must call Config.get_args() first!')

        total = len(Config.__args.proxy_judge)
        index = Config.__counter % total
        proxyjudge = Config.__args.proxy_judge[index]
        Config.__counter = (Config.__counter + 1) % total
        return proxyjudge

    def __init__(self):
        """ Parse config/CLI arguments and setup workspace """
        if Config.__args is not None:
            raise Exception('This class is a singleton!')

        Config.__args = get_args()
        self.__check_config()

    def __check_config(self):
        """ Validate configuration values """
        # if not self.__args.proxy_file and not self.__args.proxy_scrap:
        #     raise RuntimeError('You must supply a proxylist file or enable scrapping!')

        if not self.__args.proxy_judge:
            raise RuntimeError('You must specify a URL for an AZenv proxy judge.')

        if self.__args.db_max_conn <= 5:
            raise RuntimeError('Database max connections must be greater than 5.')

        if self.__args.db_batch_size <= 50:
            raise RuntimeError('Database batch size must be greater than 50.')

        if self.__args.manager_testers <= 0:
            raise RuntimeError('Proxy tester threads must be greater than 0.')

        # Validate proxy judges
        prev_ip = None
        for pj in self.__args.proxy_judge:
            local_ip = find_local_ip(pj)
            if not prev_ip:
                prev_ip = local_ip
            elif local_ip != prev_ip:
                RuntimeError(f'Proxy judge {pj}: {local_ip} '
                             f'(before: {prev_ip})')

        setattr(self.__args, 'local_ip', local_ip)


###############################################################################
# ArgParse helper class to deal with Enums.
# https://stackoverflow.com/questions/43968006/support-for-enum-arguments-in-argparse
###############################################################################

class EnumAction(configargparse.Action):
    """
    ArgParse Action for handling Enum types
    """
    def __init__(self, **kwargs):
        # Pop off the type value
        enum_type = kwargs.pop('type', None)

        # Ensure an Enum subclass is provided
        if enum_type is None:
            raise ValueError('type must be assigned an Enum when using EnumAction')
        if not issubclass(enum_type, Enum):
            raise TypeError('type must be an Enum when using EnumAction')

        # Generate choices from the Enum
        kwargs.setdefault('choices', tuple(e.name for e in enum_type))

        super(EnumAction, self).__init__(**kwargs)

        self._enum = enum_type

    def __call__(self,
                 parser: configargparse.ArgumentParser,
                 namespace: configargparse.Namespace,
                 value: Any,
                 option_string: str = None):
        # Convert value back into an Enum
        if isinstance(value, str):
            value = self._enum[value]
            setattr(namespace, self.dest, value)
        elif value is None:
            msg = f'You need to pass a value after {option_string}!'
            raise configargparse.ArgumentTypeError(msg)
        else:
            # A pretty invalid choice message will be generated by argparse
            raise configargparse.ArgumentTypeError()


###############################################################################
# ConfigArgParse definitions for current application.
# The following code should have minimal dependencies.
# https://docs.python.org/3/library/argparse.html
# Note: If the 'type' keyword is used with the 'default' keyword,
# the type converter is only applied if the default is a string.
###############################################################################

def get_args():
    default_config = []

    config_file = os.path.normpath(
        os.path.join(APP_PATH, 'config/config.ini'))

    if '-cf' not in sys.argv and '--config' not in sys.argv:
        default_config = [config_file]
    parser = configargparse.ArgParser(default_config_files=default_config)

    parser.add_argument('-cf', '--config',
                        is_config_file=True, help='Set configuration file.')
    parser.add_argument('-v', '--verbose',
                        help='Control verbosity level, e.g. -v or -vv.',
                        action='count',
                        default=0)
    parser.add_argument('--log-path',
                        help='Directory where log files are saved.',
                        default='logs',
                        type=str_path)
    parser.add_argument('--download-path',
                        help='Directory where downloaded files are saved.',
                        default='downloads',
                        type=str_path)
    parser.add_argument('-pj', '--proxy-judge',
                        action='append',
                        help='URL for AZenv script used to test proxies.',
                        default=['http://pascal.hoez.free.fr/azenv.php'])
    parser.add_argument('-ua', '--user-agent',
                        help='Browser User-Agent used. Default: random',
                        choices=['random', 'chrome', 'firefox', 'safari'],
                        default='random')

    group = parser.add_argument_group('Database')
    group.add_argument('--db-name',
                       env_var='MYSQL_DATABASE',
                       help='Name of the database to be used.',
                       required=True)
    group.add_argument('--db-user',
                       env_var='MYSQL_USER',
                       help='Username for the database.',
                       required=True)
    group.add_argument('--db-pass',
                       env_var='MYSQL_PASSWORD',
                       help='Password for the database.',
                       required=True)
    group.add_argument('--db-host',
                       env_var='MYSQL_HOST',
                       help='IP or hostname for the database.',
                       default='127.0.0.1')
    group.add_argument('--db-port',
                       env_var='MYSQL_PORT',
                       help='Port for the database.',
                       type=int, default=3306)
    group.add_argument('--db-max-conn',
                       env_var='MYSQL_MAX_CONN',
                       help='Maximum number of connections to the database.',
                       type=int, default=20)
    group.add_argument('--db-batch-size',
                       env_var='MYSQL_BATCH_SIZE',
                       help='Maximum number of rows to update per batch.',
                       type=int, default=250)

    group = parser.add_argument_group('Cleanup')
    group.add_argument('-Cp', '--cleanup-period',
                       help=('Check tests executed in the last X days. '
                             'Default: 14.'),
                       default=14,
                       type=int)
    group.add_argument('-Ctc', '--cleanup-test-count',
                       help=('Minimum number of tests to consider. '
                             'Default: 30.'),
                       default=30,
                       type=int)
    group.add_argument('-Cfr', '--cleanup-fail-ratio',
                       help=('Maximum failure ratio of tests. '
                             'Default: 1.'),
                       default=1,
                       type=float_ratio)

    group = parser.add_argument_group('Proxy Sources')
    group.add_argument('-Pf', '--proxy-file',
                       help='Filename of proxy list to verify.',
                       default=None)
    group.add_argument('-Ps', '--proxy-scrap',
                       help='Scrap webpages for proxy lists.',
                       action='store_true')
    group.add_argument('-Pp', '--proxy-protocol',
                       help='Specify proxy protocol we are testing.',
                       action=EnumAction,
                       type=ProxyProtocol)
    group.add_argument('-Pri', '--proxy-refresh-interval',
                       help=('Refresh proxylist from configured sources '
                             'every X minutes. Default: 180.'),
                       default=180,
                       type=int_minutes)
    group.add_argument('-Psi', '--proxy-scan-interval',
                       help=('Scan proxies from database every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int_minutes)
    group.add_argument('-Pic', '--proxy-ignore-country',
                       help=('Ignore proxies from countries in this list. '
                             'Use ISO 3166-1 codes. Default: CHN, ARE'),
                       nargs='*',
                       default=['CHN', 'ARE'],
                       type=str_iso3166_1)

    group = parser.add_argument_group('Output')
    group.add_argument('-Oi', '--output-interval',
                       help=('Output working proxylist every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int_minutes)
    group.add_argument('-Ol', '--output-limit',
                       help=('Maximum number of proxies to output. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Onp', '--output-no-protocol',
                       help='Proxy URL format will not include protocol.',
                       action='store_true')
    group.add_argument('-Oh', '--output-http',
                       help=('Output filename for working HTTP proxies. '
                             'To disable: None/False.'),
                       default='working_http.txt',
                       type=str_disable)
    group.add_argument('-Os', '--output-socks',
                       help=('Output filename for working SOCKS proxies. '
                             'To disable: None/False.'),
                       default='working_socks.txt',
                       type=str_disable)
    group.add_argument('-Okc', '--output-kinancity',
                       help=('Output filename for KinanCity proxylist. '
                             'Default: None (disabled).'),
                       default=None,
                       type=str_disable)
    group.add_argument('-Opc', '--output-proxychains',
                       help=('Output filename for ProxyChains proxylist. '
                             'Default: None (disabled).'),
                       default=None,
                       type=str_disable)
    group.add_argument('-Orm', '--output-rocketmap',
                       help=('Output filename for RocketMap proxylist. '
                             'Default: None (disabled).'),
                       default=None,
                       type=str_disable)

    group = parser.add_argument_group('Proxy Manager')
    group.add_argument('-Mni', '--manager-notice-interval',
                       help=('Print proxy manager statistics every X seconds. '
                             'Default: 60.'),
                       default=60,
                       type=float_seconds)
    group.add_argument('-Mt', '--manager-testers',
                       help=('Maximum concurrent proxy testing threads. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Ta', '--test-anonymity',
                       help='Test if proxy preserves anonymity.',
                       action='store_true')
    group.add_argument('-Tp', '--test-pogo',
                       help='Test if proxy can connect with PoGo API.',
                       action='store_true')

    group = parser.add_argument_group('Proxy Tester')
    group.add_argument('-Tr', '--tester-retries',
                       help=('Maximum number of web request attempts. '
                             'Default: 5.'),
                       default=5,
                       type=int)
    group.add_argument('-Tbf', '--tester-backoff-factor',
                       help=('Time factor (in seconds) by which the delay '
                             'until next retry will increase. Default: 0.5.'),
                       default=0.5,
                       type=float_seconds)
    group.add_argument('-Tt', '--tester-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float_seconds)
    group.add_argument('-Tf', '--tester-force',
                       help='Continue test execution on proxy fail.',
                       action='store_true')

    group = parser.add_argument_group('Proxy Scrapper')
    group.add_argument('-Sr', '--scrapper-retries',
                       help=('Maximum number of web request attempts. '
                             'Default: 3.'),
                       default=3,
                       type=int)
    group.add_argument('-Sbf', '--scrapper-backoff-factor',
                       help=('Time factor (in seconds) by which the delay '
                             'until next retry will increase. Default: 0.5.'),
                       default=0.5,
                       type=float_seconds)
    group.add_argument('-St', '--scrapper-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float_seconds)
    group.add_argument('-Sp', '--scrapper-proxy',
                       help=('Use this proxy for webpage scrapping. '
                             'Format: <proto>://[<user>:<pass>@]<ip>:<port> '
                             'Default: None.'),
                       default=None)
    args = parser.parse_args()

    if args.verbose:
        parser.print_values()

    # Helper attributes
    setattr(args, "app_path", APP_PATH)

    return args


def int_minutes(arg: int):
    interval = int(arg)

    if interval <= 0:
        raise ValueError('Negative time interval specified!')

    return interval * 60


def float_minutes(arg: float):
    interval = float(arg)

    if interval <= 0:
        raise ValueError('Negative time interval specified!')

    return interval * 60


def int_seconds(arg: int):
    interval = int(arg)

    if interval <= 0:
        raise ValueError('Negative time interval specified!')

    return interval


def float_seconds(arg: float):
    interval = float(arg)

    if interval <= 0:
        raise ValueError('Negative time interval specified!')

    return interval


def float_ratio(arg: float):
    ratio = float(arg)

    if ratio < 0:
        raise ValueError('Minimum percentage is 0.0!')

    if ratio > 1:
        raise ValueError('Maximum percentage is 1.0!')

    return ratio


def str_path(arg: str):
    if arg is None:
        raise ValueError('Empty path specified!')

    if os.path.isabs(arg):
        path = arg
    else:
        path = os.path.abspath(f'{APP_PATH}/{arg}')

    # Create directory if path not found
    if not os.path.exists(path):
        os.mkdir(path)
    return path


def str_disable(arg: str):
    if arg is None or arg.lower() in ['none', 'false']:
        return None

    return arg


def str_iso3166_1(arg: str):
    country = None
    if arg.isnumeric():
        country = pycountry.countries.get(numeric=arg)
    elif len(arg) == 2:
        country = pycountry.countries.get(alpha_2=arg)
    elif len(arg) == 3:
        country = pycountry.countries.get(alpha_3=arg)
    else:
        print(arg)
        msg = 'invalid ISO 3166-1 code format'
        raise configargparse.ArgumentTypeError(msg)

    if country is None:
        msg = f'"{arg}" unknown ISO 3166-1 code'
        raise configargparse.ArgumentTypeError(msg)

    return country.alpha_2
