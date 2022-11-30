# Python Proxy Scanner

Scrap proxy lists from the web and test their connectivity.

## Feature Support

- Multi-threaded proxy tester.
- Automatic proxy scrapper from web pages.
- Supports HTTP and SOCKS protocols.
- Test proxy anonymity using an external proxy judge.
- Measures proxy average latency (response time).
- MySQL database for keeping proxy status.
- Output final proxy list in several formats: Normal, ProxyChains.
- Docker container configuration included.

## Useful developer resources

- [ArgParse](https://docs.python.org/3/library/argparse.html)
- [ConfigArgParse](https://github.com/bw2/ConfigArgParse)
- [Peewee ORM](http://docs.peewee-orm.com/en/latest/)
- [Peewee ORM: Multi-Threaded Applications](http://docs.peewee-orm.com/en/latest/peewee/database.html#multi-threaded-applications)
- [Querying the top N objects per group with Peewee ORM](https://charlesleifer.com/blog/querying-the-top-n-objects-per-group-with-peewee-orm/)
- [MySQL JOIN the most recent row only?](https://stackoverflow.com/a/35965649/1546848)
- [Python Requests](https://requests.readthedocs.io/en/master/)
- [urllib3](https://urllib3.readthedocs.io/en/latest/)
- [urllib3 - set max retries](https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request)
- [Conversion from IP string to integer and backwards](https://stackoverflow.com/a/13294427)
- [Coerce INET_ATON](https://github.com/coleifer/peewee/issues/342)
- [ProxyChains](https://github.com/haad/proxychains)
- [IP2Location python library](https://www.ip2location.com/development-libraries/ip2location/python) - [GitHub](https://github.com/chrislim2888/IP2Location-Python)
- [BeautifulSoup](https://beautiful-soup-4.readthedocs.io/en/latest/)
- [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- [Jinja2](https://jinja2docs.readthedocs.io/en/stable/)

## Credits
This site or product includes IP2Location LITE data available from [http://www.ip2location.com](http://www.ip2location.com).

Originally based on [neskk/PoGo-Proxies](https://github.com/neskk/PoGo-Proxies).

## Disclaimer

This software allows scrapping of public proxies and only provides access to them.
We're not responsible for these proxies and we're not responsible for what users do with them.

## Requirements
- Python 3.7+
- MySQL 5.7+
- beautifulsoup4==4.9.0
- configargparse==1.2.3
- pymysql==0.9.3
- peewee==3.13.3
- PySocks==1.7.1
- requests==2.23.0
- ip2location==8.4.1
- pycountry==22.3.5
- ~~jsbeautifier==1.11.0~~ We're using a modified version of [packer.py](https://github.com/beautify-web/js-beautify/blob/master/python/jsbeautifier/unpackers/packer.py)

## TODO
- Cleanup queries - proxies stuck on testing status + old tests + old and bad proxies.
- Add flask webserver for web interface/API development.
    - **This should replace file output.**
    - Consider importing files through web interface as well.
- Check proxy reputation on blacklist/RBL sites (e.g: http://www.anti-abuse.org/, https://mxtoolbox.com/blacklists.aspx, https://tinycp.com/page/show/rbl-check)
- Consider incremental sleep when testers are idle / reducing re-test cooldown period.
- Scrapper database model to hold stats and general activity.
- Add support for web scrapping with selenium + webdriver.
- Resolve hostname and IP block data.
- Separate concerns: testing, scrapping and interface/UI.
- Proxy discovery: when a tester thread is idle we can check variations of known proxies (e.g. IP range, port range).

## Usage

```
usage: start.py [-h] [-cf CONFIG] [-v] [--log-path LOG_PATH] [--download-path DOWNLOAD_PATH] [--tmp-path TMP_PATH] [-pj PROXY_JUDGE] [-ua {random,chrome,firefox,safari}] --db-name DB_NAME --db-user DB_USER --db-pass DB_PASS [--db-host DB_HOST] [--db-port DB_PORT]
                [-Pf PROXY_FILE] [-Ps] [-Pp {HTTP,SOCKS4,SOCKS5}] [-Pri PROXY_REFRESH_INTERVAL] [-Psi PROXY_SCAN_INTERVAL] [-Pic [PROXY_IGNORE_COUNTRY ...]] [-Oi OUTPUT_INTERVAL] [-Ol OUTPUT_LIMIT] [-Onp] [-Oh OUTPUT_HTTP] [-Os OUTPUT_SOCKS]
                [-Okc OUTPUT_KINANCITY] [-Opc OUTPUT_PROXYCHAINS] [-Orm OUTPUT_ROCKETMAP] [-Mni MANAGER_NOTICE_INTERVAL] [-Mt MANAGER_TESTERS] [-Ta] [-Tp] [-Tr TESTER_RETRIES] [-Tbf TESTER_BACKOFF_FACTOR] [-Tt TESTER_TIMEOUT] [-Tf] [-Sr SCRAPPER_RETRIES]
                [-Sbf SCRAPPER_BACKOFF_FACTOR] [-St SCRAPPER_TIMEOUT] [-Sp SCRAPPER_PROXY]

optional arguments:
  -h, --help            show this help message and exit
  -cf CONFIG, --config CONFIG
                        Set configuration file.
  -v, --verbose         Control verbosity level, e.g. -v or -vv.
  --log-path LOG_PATH   Directory where log files are saved.
  --download-path DOWNLOAD_PATH
                        Directory where downloaded files are saved.
  --tmp-path TMP_PATH   Directory where temporary files are saved.
  -pj PROXY_JUDGE, --proxy-judge PROXY_JUDGE
                        URL for AZenv script used to test proxies.
  -ua {random,chrome,firefox,safari}, --user-agent {random,chrome,firefox,safari}
                        Browser User-Agent used. Default: random

Database:
  --db-name DB_NAME     Name of the database to be used. [env var: MYSQL_DATABASE]
  --db-user DB_USER     Username for the database. [env var: MYSQL_USER]
  --db-pass DB_PASS     Password for the database. [env var: MYSQL_PASSWORD]
  --db-host DB_HOST     IP or hostname for the database. [env var: MYSQL_HOST]
  --db-port DB_PORT     Port for the database. [env var: MYSQL_PORT]

Proxy Sources:
  -Pf PROXY_FILE, --proxy-file PROXY_FILE
                        Filename of proxy list to verify.
  -Ps, --proxy-scrap    Scrap webpages for proxy lists.
  -Pp {HTTP,SOCKS4,SOCKS5}, --proxy-protocol {HTTP,SOCKS4,SOCKS5}
                        Specify proxy protocol we are testing.
  -Pri PROXY_REFRESH_INTERVAL, --proxy-refresh-interval PROXY_REFRESH_INTERVAL
                        Refresh proxylist from configured sources every X minutes. Default: 180.
  -Psi PROXY_SCAN_INTERVAL, --proxy-scan-interval PROXY_SCAN_INTERVAL
                        Scan proxies from database every X minutes. Default: 60.
  -Pic [PROXY_IGNORE_COUNTRY ...], --proxy-ignore-country [PROXY_IGNORE_COUNTRY ...]
                        Ignore proxies from countries in this list. Use ISO 3166-1 codes. Default: CHN, ARE

Output:
  -Oi OUTPUT_INTERVAL, --output-interval OUTPUT_INTERVAL
                        Output working proxylist every X minutes. Default: 60.
  -Ol OUTPUT_LIMIT, --output-limit OUTPUT_LIMIT
                        Maximum number of proxies to output. Default: 100.
  -Onp, --output-no-protocol
                        Proxy URL format will not include protocol.
  -Oh OUTPUT_HTTP, --output-http OUTPUT_HTTP
                        Output filename for working HTTP proxies. To disable: None/False.
  -Os OUTPUT_SOCKS, --output-socks OUTPUT_SOCKS
                        Output filename for working SOCKS proxies. To disable: None/False.
  -Okc OUTPUT_KINANCITY, --output-kinancity OUTPUT_KINANCITY
                        Output filename for KinanCity proxylist. Default: None (disabled).
  -Opc OUTPUT_PROXYCHAINS, --output-proxychains OUTPUT_PROXYCHAINS
                        Output filename for ProxyChains proxylist. Default: None (disabled).
  -Orm OUTPUT_ROCKETMAP, --output-rocketmap OUTPUT_ROCKETMAP
                        Output filename for RocketMap proxylist. Default: None (disabled).

Proxy Manager:
  -Mni MANAGER_NOTICE_INTERVAL, --manager-notice-interval MANAGER_NOTICE_INTERVAL
                        Print proxy manager statistics every X seconds. Default: 60.
  -Mt MANAGER_TESTERS, --manager-testers MANAGER_TESTERS
                        Maximum concurrent proxy testing threads. Default: 100.
  -Ta, --test-anonymity
                        Test if proxy preserves anonymity.
  -Tp, --test-pogo      Test if proxy can connect with PoGo API.

Proxy Tester:
  -Tr TESTER_RETRIES, --tester-retries TESTER_RETRIES
                        Maximum number of web request attempts. Default: 5.
  -Tbf TESTER_BACKOFF_FACTOR, --tester-backoff-factor TESTER_BACKOFF_FACTOR
                        Time factor (in seconds) by which the delay until next retry will increase. Default: 0.5.
  -Tt TESTER_TIMEOUT, --tester-timeout TESTER_TIMEOUT
                        Connection timeout in seconds. Default: 5.
  -Tf, --tester-force   Continue test execution on proxy fail.

Proxy Scrapper:
  -Sr SCRAPPER_RETRIES, --scrapper-retries SCRAPPER_RETRIES
                        Maximum number of web request attempts. Default: 3.
  -Sbf SCRAPPER_BACKOFF_FACTOR, --scrapper-backoff-factor SCRAPPER_BACKOFF_FACTOR
                        Time factor (in seconds) by which the delay until next retry will increase. Default: 0.5.
  -St SCRAPPER_TIMEOUT, --scrapper-timeout SCRAPPER_TIMEOUT
                        Connection timeout in seconds. Default: 5.
  -Sp SCRAPPER_PROXY, --scrapper-proxy SCRAPPER_PROXY
                        Use this proxy for webpage scrapping. Format: <proto>://[<user>:<pass>@]<ip>:<port> Default: None.

Args that start with '--' (eg. -v) can also be set in a config file (app\config\config.ini or specified via -cf). Config file syntax allows: key=value, flag=true, stuff=[a,b,c] (for details, see syntax at https://goo.gl/R74nmi).
If an arg is specified in more than one place, then commandline values override environment variables which override config file values which override defaults.
```


## Debugging with VS Code while using Docker containers

1. Launch the containers with the task: `up-debug`
2. Attach to the container using the launch config: `Python: Remote Attach`
3. You should be able to debug, add breakpoints, etc.

### Sources

- Customize the Docker extension: https://code.visualstudio.com/docs/containers/reference
- Debug containerized apps: https://code.visualstudio.com/docs/containers/debug-common
- Use Docker Compose: https://code.visualstudio.com/docs/containers/docker-compose
- Debug Python within a container: https://code.visualstudio.com/docs/containers/debug-python

### tasks.json:

```json
{
    "label": "up-debug",
    "type": "docker-compose",
    "dockerCompose": {
        "up": {
            "detached": true,
            "build": true,
        },
        "files": [
            "${workspaceFolder}/docker-compose.yml",
            "${workspaceFolder}/docker-compose.debug.yml"
        ]
    }
},
{
    "label": "up-database",
    "type": "docker-compose",
    "dockerCompose": {
        "up": {
            "detached": true,
            "build": true,
            "services": ["db"]
        },
        "files": [
            "${workspaceFolder}/docker-compose.yml",
            "${workspaceFolder}/docker-compose.debug.yml"
        ]
    }
}
```

### launch.json

```json
{
    "name": "Python: Remote Attach",
    "type": "python",
    "request": "attach",
    "connect": {
        "host": "localhost",
        "port": 5678
    },
    "pathMappings": [
        {
            "localRoot": "${workspaceFolder}/app",
            "remoteRoot": "/usr/src/app"
        }
    ]
}
```
