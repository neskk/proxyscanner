#!/usr/bin/python
# -*- coding: utf-8 -*-

import configargparse
import os
import sys


class Config:
    """ Singleton class that parses and holds all the configuration arguments """
    __args = None

    @staticmethod
    def get_args():
        """ Static access method """
        if Config.__args == None:
            Config()
        return Config.__args

    def __init__(self):
        """ Parse config/cli arguments and setup workspace """
        if Config.__args != None:
            raise Exception("This class is a singleton!")
        else:
            Config.__args = get_args()
            self.__setup_workspace()

    def __setup_workspace(self):
        if not os.path.exists(self.__args.log_path):
            # Create directory for log files.
            os.mkdir(self.__args.log_path)

        if not os.path.exists(self.__args.download_path):
            # Create directory for downloaded files.
            os.mkdir(self.__args.download_path)


def get_args():
    default_config = []
    app_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..'))
    config_file = os.path.normpath(
        os.path.join(app_path, 'config/config.ini'))

    if '-cf' not in sys.argv and '--config' not in sys.argv:
        default_config = [config_file]
    parser = configargparse.ArgParser(default_config_files=default_config)

    parser.add_argument('-cf', '--config',
                        is_config_file=True, help='Set configuration file.')
    parser.add_argument('-v', '--verbose',
                        help='Run in the verbose mode.',
                        action='store_true')
    parser.add_argument('--log-path',
                        help='Directory where log files are saved.',
                        default='logs')
    parser.add_argument('--download-path',
                        help='Directory where download files are saved.',
                        default='downloads')
    parser.add_argument('-pj', '--proxy-judge',
                        help='URL for AZenv script used to test proxies.',
                        default='http://pascal.hoez.free.fr/azenv.php')

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

    group = parser.add_argument_group('Proxy Sources')
    group.add_argument('-Pf', '--proxy-file',
                       help='Filename of proxy list to verify.',
                       default=None)
    group.add_argument('-Ps', '--proxy-scrap',
                       help='Scrap webpages for proxy lists.',
                       default=False,
                       action='store_true')
    group.add_argument('-Pp', '--proxy-protocol',
                       help=('Specify proxy protocol we are testing. ' +
                             'Default: socks.'),
                       default='socks',
                       choices=('http', 'socks', 'all'))
    group.add_argument('-Pri', '--proxy-refresh-interval',
                       help=('Refresh proxylist from configured sources '
                             'every X minutes. Default: 180.'),
                       default=180,
                       type=int)
    group.add_argument('-Psi', '--proxy-scan-interval',
                       help=('Scan proxies from database every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Pic', '--proxy-ignore-country',
                       help=('Ignore proxies from countries in this list. '
                             'Default: ["china"]'),
                       default=['china'],
                       action='append')

    group = parser.add_argument_group('Output')
    group.add_argument('-Oi', '--output-interval',
                       help=('Output working proxylist every X minutes. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Ol', '--output-limit',
                       help=('Maximum number of proxies to output. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Onp', '--output-no-protocol',
                       help='Proxy URL format will not include protocol.',
                       default=False,
                       action='store_true')
    group.add_argument('-Oh', '--output-http',
                       help=('Output filename for working HTTP proxies. '
                             'To disable: None/False.'),
                       default='working_http.txt')
    group.add_argument('-Os', '--output-socks',
                       help=('Output filename for working SOCKS proxies. '
                             'To disable: None/False.'),
                       default='working_socks.txt')
    group.add_argument('-Okc', '--output-kinancity',
                       help=('Output filename for KinanCity proxylist. '
                             'Default: None (disabled).'),
                       default=None)
    group.add_argument('-Opc', '--output-proxychains',
                       help=('Output filename for ProxyChains proxylist. '
                             'Default: None (disabled).'),
                       default=None)
    group.add_argument('-Orm', '--output-rocketmap',
                       help=('Output filename for RocketMap proxylist. '
                             'Default: None (disabled).'),
                       default=None)

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
                       type=float)
    group.add_argument('-Tt', '--tester-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float)
    group.add_argument('-Tmc', '--tester-max-concurrency',
                       help=('Maximum concurrent proxy testing threads. '
                             'Default: 100.'),
                       default=100,
                       type=int)
    group.add_argument('-Tda', '--tester-disable-anonymity',
                       help='Disable anonymity proxy test.',
                       default=False,
                       action='store_true')
    group.add_argument('-Tni', '--tester-notice-interval',
                       help=('Print proxy tester statistics every X seconds. '
                             'Default: 60.'),
                       default=60,
                       type=int)
    group.add_argument('-Tpv', '--tester-pogo-version',
                       help='PoGo API version currently required by Niantic.',
                       default='0.223.0')

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
                       type=float)
    group.add_argument('-St', '--scrapper-timeout',
                       help='Connection timeout in seconds. Default: 5.',
                       default=5,
                       type=float)
    group.add_argument('-Sp', '--scrapper-proxy',
                       help=('Use this proxy for webpage scrapping. '
                             'Format: <proto>://[<user>:<pass>@]<ip>:<port> '
                             'Default: None.'),
                       default=None)
    args = parser.parse_args()

    if args.verbose:
        parser.print_values()

    return args
