#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import queue
from threading import Event, Thread
import time

from peewee import DatabaseProxy, DatabaseError, OperationalError
from playhouse.pool import PooledMySQLDatabase, MaxConnectionsExceeded
from playhouse.migrate import migrate, MySQLMigrator

from .config import Config
from .models import Proxy, ProxyTest, DBConfig

log = logging.getLogger(__name__)


###############################################################################
# Database initialization
# https://docs.peewee-orm.com/en/latest/peewee/database.html#dynamically-defining-a-database
# https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#database-url
# https://docs.peewee-orm.com/en/latest/peewee/database.html#setting-the-database-at-run-time
###############################################################################
class Database():
    BATCH_SIZE = 250  # TODO: move to Config argparse
    DB = DatabaseProxy()
    MODELS = [Proxy, ProxyTest, DBConfig]
    SCHEMA_VERSION = 1

    def __init__(self):
        """ Create a pooled connection to MySQL database """
        self.args = Config.get_args()

        log.info('Connecting to MySQL database on '
                 f'{self.args.db_host}:{self.args.db_port}...')

        # https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pool-apis
        database = PooledMySQLDatabase(
            self.args.db_name,
            host=self.args.db_host,
            port=self.args.db_port,
            user=self.args.db_user,
            password=self.args.db_pass,
            charset='utf8mb4',
            autoconnect=False,
            max_connections=self.args.db_max_conn,  # use None for unlimited
            stale_timeout=180,  # use None to disable
            timeout=10)  # 0 blocks indefinitely

        # Initialize DatabaseProxy
        self.DB.initialize(database)

        # Bind models to this database
        self.DB.bind(self.MODELS)

        try:
            self.DB.connect()
            self.verify_database_schema()
            self.verify_table_encoding()
        except OperationalError as e:
            log.error('Unable to connect to database: %s', e)
        except DatabaseError as e:
            log.exception('Failed to initalize database: %s', e)
        finally:
            self.DB.close()

    #  https://docs.peewee-orm.com/en/latest/peewee/api.html#Database.create_tables
    def create_tables(self):
        """ Create tables in the database (skips existing) """
        table_names = ', '.join([m.__name__ for m in self.MODELS])
        log.info('Creating database tables: %s', table_names)
        self.DB.create_tables(self.MODELS, safe=True)  # safe adds if not exists
        # Create schema version key
        DBConfig.insert_schema_version(self.SCHEMA_VERSION)
        log.info('Database schema created.')

    #  https://docs.peewee-orm.com/en/latest/peewee/api.html#Database.drop_tables
    def drop_tables(self):
        """ Drop all the tables in the database """
        table_names = ', '.join([m.__name__ for m in self.MODELS])
        log.info('Dropping database tables: %s', table_names)
        self.DB.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
        self.DB.drop_tables(self.MODELS, safe=True)
        self.DB.execute_sql('SET FOREIGN_KEY_CHECKS=1;')
        log.info('Database schema deleted.')

    # https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#schema-migrations
    def migrate_database_schema(self, old_ver):
        """ Migrate database schema """
        log.info(f'Migrating schema version {old_ver} to {self.SCHEMA_VERSION}.')
        migrator = MySQLMigrator(self.DB)

        if old_ver < 2:
            migrate(migrator.rename_table('db_config', 'db_config'))

        log.info('Schema migration complete.')

    def verify_database_schema(self):
        """ Verify if database is properly initialized """
        if not DBConfig.table_exists():
            self.create_tables()
            return

        DBConfig.init_lock()
        db_ver = DBConfig.get_schema_version()

        # Check if schema migration is required
        if db_ver < self.SCHEMA_VERSION:
            self.migrate_database_schema(db_ver)
            DBConfig.update_schema_version(self.SCHEMA_VERSION)
        elif db_ver > self.SCHEMA_VERSION:
            raise RuntimeError(
                f'Unsupported schema version: {db_ver} '
                f'(code requires: {self.SCHEMA_VERSION})')

    def verify_table_encoding(self):
        """ Verify if table collation is valid """
        change_tables = self.DB.execute_sql(
            'SELECT table_name FROM information_schema.tables WHERE '
            'table_collation != "utf8mb4_unicode_ci" '
            f'AND table_schema = "{self.args.db_name}";')

        tables = self.DB.execute_sql('SHOW tables;')

        if change_tables.rowcount > 0:
            log.info('Changing collation and charset on '
                     f'{change_tables.rowcount} tables.')

            if change_tables.rowcount == tables.rowcount:
                log.info('Changing whole database, this might a take while.')

            self.DB.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
            for table in change_tables:
                log.debug('Changing collation and charset on '
                          f'table {table[0]}.')
                self.DB.execute_sql(
                    f'ALTER TABLE {table[0]} CONVERT TO '
                    'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
            self.DB.execute_sql('SET FOREIGN_KEY_CHECKS=1;')

    def print_stats(self):
        in_use = len(self.DB._in_use)
        available = len(self.DB._connections)
        log.info('Database connections: '
                 f'{in_use} in use and {available} available.')


class DatabaseQueue():
    """ Singleton class that holds database queues """
    __instance = None

    @staticmethod
    def get_db_queue():
        """ Static access method """
        if DatabaseQueue.__instance is None:
            DatabaseQueue.__instance = DatabaseQueue()
        return DatabaseQueue.__instance

    def __init__(self):
        """
        Manage database update queues
        """
        if DatabaseQueue.__instance is not None:
            raise Exception('This class is a singleton!')

        self.args = Config.get_args()
        self.interrupt = Event()

        # Initialize queues
        self.test_queue = queue.Queue(maxsize=self.args.manager_testers * 2)
        self.proxy_queue = queue.Queue(maxsize=self.args.manager_testers * 2)
        self.proxytest_queue = queue.Queue(maxsize=self.args.manager_testers * 10)

    def start(self):
        """
        Start database queue threads.
        Note: thread calling this method needs to remain alive.
        """
        self.test_queue_thread = Thread(
            name='testing-queue',
            target=self.testing_loop,
            daemon=False)
        self.test_queue_thread.start()

        self.upsert_proxy_thread = Thread(
            name='upsert-proxy',
            target=self.upsert_proxy_loop,
            daemon=False)
        self.upsert_proxy_thread.start()

        self.upsert_proxytest_thread = Thread(
            name='upsert-proxytest',
            target=self.upsert_proxytest_loop,
            daemon=False)
        self.upsert_proxytest_thread.start()

    def stop(self):
        self.interrupt.set()
        log.info('Waiting for queue threads to finish...')
        self.test_queue_thread.join()
        self.upsert_proxy_thread.join()
        self.upsert_proxytest_thread.join()
        log.info('Database queue threads shutdown.')

    def get_proxy(self):
        try:
            proxy = self.test_queue.get(timeout=1)
            return proxy
        except queue.Empty:
            return None

    def fill_test_queue(self):
        protocol = self.args.proxy_protocol
        num = self.test_queue.maxsize - self.test_queue.qsize()

        if num == 0:
            time.sleep(1)
            return

        if not DBConfig.lock_database(self.args.local_ip):
            time.sleep(1)
            return

        query = Proxy.need_scan(limit=num, protocols=protocol)
        proxy_ids = []
        for proxy in query:
            proxy_ids.append(proxy.id)
            self.test_queue.put(proxy)

        row_count = Proxy.bulk_lock(proxy_ids)
        DBConfig.unlock_database(self.args.local_ip)
        return row_count

    def release_test_queue(self):
        log.debug('Releasing proxy test queue...')
        proxy_ids = []
        while not self.test_queue.empty():
            proxy = self.test_queue.get(block=False)
            proxy_ids.append(proxy.id)

        return Proxy.bulk_unlock(proxy_ids)

    def update_proxy(self, proxy):
        self.proxy_queue.put(proxy, timeout=1)

    def update_proxytest(self, proxytest):
        self.proxytest_queue.put(proxytest, timeout=1)

    def upsert_proxy_queue(self, threshold=0):
        threshold = min(self.proxy_queue.maxsize-1, threshold)
        if self.proxy_queue.qsize() < threshold:
            return

        proxy_batch = []
        while not self.proxy_queue.empty():
            proxy = self.proxy_queue.get(block=False)
            proxy_batch.append(proxy)

        update_fields = [
            'status',
            'latency',
            'test_count',
            'fail_count',
            'country',
            'modified'
        ]
        Proxy.bulk_update(
            proxy_batch,
            fields=update_fields,
            batch_size=Database.BATCH_SIZE)

    def upsert_proxytest_queue(self, threshold=0):
        threshold = min(self.proxytest_queue.maxsize-1, threshold)
        if self.proxytest_queue.qsize() < threshold:
            return

        proxytest_batch = []
        while not self.proxytest_queue.empty():
            proxytest = self.proxytest_queue.get(block=False)
            proxytest_batch.append(proxytest)

        ProxyTest.bulk_create(proxytest_batch, batch_size=Database.BATCH_SIZE)

    def print_stats(self):
        log.info(f'Test Queue: {self.test_queue.qsize()}')
        log.info(f'Upsert Proxy Queue: {self.proxy_queue.qsize()}')
        log.info(f'Upsert ProxyTest Queue: {self.proxytest_queue.qsize()}')

    def testing_loop(self):
        log.debug('Test queue thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Giving up, unable to upsert Proxy queue.')
                break

            if self.interrupt.is_set():
                break

            try:
                Proxy.database().connect()
                self.fill_test_queue()
                error_count = 0
            except DatabaseError as e:
                log.error(f'Failed to fill test queue: {e}')
                error_count += 1
                time.sleep(1.0)
            except MaxConnectionsExceeded as e:
                log.error(f'Failed to acquire a database connection: {e}')
                error_count += 1
                time.sleep(1.0)
            finally:
                Proxy.database().close()

        try:
            Proxy.database().connect()
            self.release_test_queue()
        except DatabaseError as e:
            log.error(f'Failed to release test queue: {e}')
        except MaxConnectionsExceeded as e:
            log.error(f'Failed to acquire a database connection: {e}')
        finally:
            Proxy.database().close()

        log.debug('Test queue thread shutdown.')

    def upsert_proxy_loop(self):
        log.debug('Proxy upsert thread started.')
        error_count = 0
        while True:
            try:
                if error_count > 4:
                    log.error('Giving up, unable to upsert Proxy queue.')
                    break
                Proxy.database().connect()
                if self.interrupt.is_set():
                    # make sure we upsert all records
                    self.upsert_proxy_queue()
                else:
                    self.upsert_proxy_queue(10)

                error_count = 0
                if self.interrupt.is_set():
                    break
            except DatabaseError as e:
                log.error(f'Failed to upsert Proxy queue: {e}')
                error_count += 1
                time.sleep(1.0)
            except MaxConnectionsExceeded as e:
                log.error(f'Failed to acquire a database connection: {e}')
                error_count += 1
                time.sleep(1.0)
            finally:
                Proxy.database().close()

        log.debug('Proxy upsert thread shutdown.')

    def upsert_proxytest_loop(self):
        log.debug('ProxyTest upsert thread started.')
        error_count = 0
        while True:
            try:
                if error_count > 4:
                    log.error('Giving up, unable to upsert ProxyTest queue.')
                Proxy.database().connect()
                if self.interrupt.is_set():
                    # make sure we upsert all records
                    self.upsert_proxytest_queue()
                else:
                    self.upsert_proxytest_queue(10)

                error_count = 0
                if self.interrupt.is_set():
                    break
            except DatabaseError as e:
                log.error(f'Failed to upsert ProxyTest queue: {e}')
                error_count += 1
                time.sleep(1.0)
            except MaxConnectionsExceeded as e:
                log.error(f'Failed to acquire a database connection: {e}')
                error_count += 1
                time.sleep(1.0)
            finally:
                Proxy.database().close()

        log.debug('ProxyTest upsert thread shutdown.')

    def cleanup_loop(self):
        log.debug('Proxy cleanup thread started.')
        while True:
            try:
                if self.interrupt.is_set():
                    break
                Proxy.database().connect()
                Proxy.delete_failed(
                    age_days=self.args.cleanup_period,
                    test_count=self.args.cleanup_test_count,
                    fail_rate=self.args.cleanup_fail_ratio,
                    limit=10)
                time.sleep(60)

            except DatabaseError as e:
                log.error(f'Failed to delete bad proxies: {e}')
                if self.interrupt.is_set():
                    break
                time.sleep(30.0)
            except MaxConnectionsExceeded as e:
                log.error(f'Failed to acquire a database connection: {e}')
                break
            finally:
                Proxy.database().close()

        log.debug('Proxy cleanup thread shutdown.')

    # TODO: create a loop to bulk_insert proxies from scrappers
    # TODO: fix upsert queues to avoid:
    # (1213, 'Deadlock found when trying to get lock; try restarting transaction')
