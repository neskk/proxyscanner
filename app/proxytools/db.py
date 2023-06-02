#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import queue
import time
from threading import Event, Thread

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


class InsertProxyThread(Thread):
    def __init__(self, db_queue) -> None:
        Thread.__init__(self, name='insert-proxy', daemon=False)
        self.db_queue = db_queue
        self.args = db_queue.args
        self.interrupt = db_queue.interrupt
        self.backlog = []
        self.queue = queue.Queue()

    def print_stats(self):
        log.info(
            f'Insert Proxy Queue: {self.queue.qsize()} '
            f'(backlog: {len(self.backlog)})')

    def put(self, proxy: Proxy):
        self.queue.put(proxy, block=False)

    def put_list(self, proxylist: list):
        for proxy in proxylist:
            self.queue.put(proxy, block=False)

    def update_db(self):
        if self.queue.qsize() + len(self.backlog) < 1:
            time.sleep(1.0)
            return True

        while not self.queue.empty():
            proxy = self.queue.get(block=False)
            self.backlog.append(proxy)

        try:
            Proxy.database().connect()
            row_count = 0
            with Proxy.database().atomic():
                for idx in range(0, len(self.backlog), Database.BATCH_SIZE):
                    batch = self.backlog[idx:idx + Database.BATCH_SIZE]
                    query = (Proxy
                             .insert_many(batch)
                             .on_conflict(preserve=[
                                    Proxy.username,
                                    Proxy.password,
                                    Proxy.protocol,
                                    Proxy.modified
                                ]))
                    query = query.as_rowcount()
                    row_count += query.execute()

            log.debug(f'Inserted {row_count} proxies.')
            self.backlog.clear()
            return True
        except DatabaseError as e:
            log.warning(f'Failed to insert proxies: {e}')
        except MaxConnectionsExceeded as e:
            log.warning(f'Failed to acquire a database connection: {e}')
        finally:
            Proxy.database().close()

        return False

    def run(self) -> None:
        log.debug('Proxy insert thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Unable to insert proxies.')
                self.interrupt.set()
                break

            if not self.update_db():
                error_count += 1
                time.sleep(1.0 * error_count)
                continue

            error_count = 0
            if self.interrupt.is_set():
                break

        self.update_db()
        log.debug('Proxy insert thread shutdown.')


class TestingThread(Thread):
    def __init__(self, db_queue) -> None:
        Thread.__init__(self, name='lock-proxy', daemon=False)
        self.db_queue = db_queue
        self.args = db_queue.args
        self.interrupt = db_queue.interrupt
        self.queue = queue.Queue(maxsize=self.args.manager_testers * 2)

    def print_stats(self):
        log.info(f'Testing Queue: {self.queue.qsize()}')

    def free_slots(self):
        return self.queue.maxsize - self.queue.qsize()

    def get_proxy(self) -> Proxy:
        try:
            proxy = self.queue.get(timeout=1)
            return proxy
        except queue.Empty:
            return None

    def fill_queue(self):
        protocol = self.args.proxy_protocol
        free_slots = self.queue.maxsize - self.queue.qsize()
        if free_slots == 0:
            time.sleep(1.0)
            return True

        if not self.db_queue.lock_database():
            time.sleep(1.0)
            return True

        try:
            Proxy.database().connect()
            query = Proxy.need_scan(limit=free_slots, protocols=protocol)
            proxy_ids = []
            for proxy in query:
                proxy_ids.append(proxy.id)
                self.queue.put(proxy)
            Proxy.bulk_lock(proxy_ids)
            return True
        except DatabaseError as e:
            log.warning(f'Failed to fill test queue: {e}')
        except MaxConnectionsExceeded as e:
            log.warning(f'Failed to acquire a database connection: {e}')
        finally:
            self.db_queue.unlock_database()
            Proxy.database().close()

        return False

    def release_queue(self):
        proxy_ids = []
        while not self.queue.empty():
            proxy = self.queue.get(block=False)
            proxy_ids.append(proxy.id)

        try:
            Proxy.database().connect()
            row_count = Proxy.bulk_unlock(proxy_ids)
            log.debug(f'Released {row_count} proxies from testing.')
            return True
        except DatabaseError as e:
            log.error(f'Failed to release testing queue: {e}')
        except MaxConnectionsExceeded as e:
            log.error(f'Failed to acquire a database connection: {e}')
        finally:
            Proxy.database().close()

        log.warning(f'Failed to release {len(proxy_ids)} proxies.')
        return False

    def run(self) -> None:
        log.debug('Test queue thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Unable to get proxies to test.')
                self.interrupt.set()
                break

            if self.interrupt.is_set():
                break

            result = self.fill_queue()

            if not result:
                error_count += 1
                time.sleep(1.0 * error_count)
                continue

            error_count = 0

        self.release_queue()
        log.debug('Test queue thread shutdown.')


class UpdateProxyThread(Thread):
    def __init__(self, db_queue, threshold) -> None:
        Thread.__init__(self, name='update-proxy', daemon=False)
        self.db_queue = db_queue
        self.args = db_queue.args
        self.interrupt = db_queue.interrupt
        self.threshold = threshold
        self.backlog = []
        self.queue = queue.Queue(maxsize=self.args.manager_testers * 10)

    def print_stats(self):
        log.info(
            f'Update Proxy Queue: {self.queue.qsize()} '
            f'(backlog: {len(self.backlog)})')

    def put(self, proxy: Proxy):
        self.queue.put(proxy, timeout=1)

    def update_db(self, threshold=0):
        threshold = min(self.queue.maxsize-1, threshold)
        if self.queue.qsize() + len(self.backlog) < threshold:
            time.sleep(1.0)
            return True

        while not self.queue.empty():
            proxy = self.queue.get(block=False)
            self.backlog.append(proxy)

        try:
            Proxy.database().connect()
            with Proxy.database().atomic():
                Proxy.bulk_update(
                    self.backlog,
                    fields=[
                        'status',
                        'latency',
                        'test_count',
                        'fail_count',
                        'country',
                        'modified'
                    ],
                    batch_size=Database.BATCH_SIZE)
                self.backlog.clear()
                return True
        except DatabaseError as e:
            log.warning(f'Failed to update Proxy queue: {e}')
        except MaxConnectionsExceeded as e:
            log.warning(f'Failed to acquire a database connection: {e}')
        finally:
            Proxy.database().close()

        return False

    def run(self) -> None:
        log.debug('Proxy update thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Unable to update Proxy queue.')
                self.interrupt.set()
                break

            if self.interrupt.is_set():
                threshold = 0
            else:
                threshold = self.threshold

            if not self.update_db(threshold):
                error_count += 1
                time.sleep(1.0 * error_count)
                continue

            error_count = 0
            if self.interrupt.is_set():
                break

        self.update_db()
        log.debug('Proxy update thread shutdown.')


class UpdateProxyTestThread(Thread):
    def __init__(self, db_queue, threshold) -> None:
        Thread.__init__(self, name='update-proxytest', daemon=False)
        self.db_queue = db_queue
        self.args = db_queue.args
        self.interrupt = db_queue.interrupt
        self.threshold = threshold
        self.backlog = []
        self.queue = queue.Queue(maxsize=self.args.manager_testers * 50)

    def print_stats(self):
        log.info(
            f'Update ProxyTest Queue: {self.queue.qsize()} '
            f'(backlog: {len(self.backlog)})')

    def put(self, proxytest: ProxyTest):
        self.queue.put(proxytest, timeout=1)

    def update_db(self, threshold=0):
        threshold = min(self.queue.maxsize-1, threshold)
        if self.queue.qsize() + len(self.backlog) < threshold:
            time.sleep(1.0)
            return True

        while not self.queue.empty():
            proxy = self.queue.get(block=False)
            self.backlog.append(proxy)

        try:
            ProxyTest.database().connect()
            with ProxyTest.database().atomic():
                ProxyTest.bulk_create(
                    self.backlog,
                    batch_size=Database.BATCH_SIZE)
                self.backlog.clear()
                return True
        except DatabaseError as e:
            log.warning(f'Failed to update ProxyTest queue: {e}')
        except MaxConnectionsExceeded as e:
            log.warning(f'Failed to acquire a database connection: {e}')
        finally:
            ProxyTest.database().close()

        return False

    def run(self) -> None:
        log.debug('ProxyTest update thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Unable to update ProxyTest queue.')
                self.interrupt.set()
                break

            if self.interrupt.is_set():
                threshold = 0
            else:
                threshold = self.threshold

            if not self.update_db(threshold):
                error_count += 1
                time.sleep(1.0 * error_count)
                continue

            error_count = 0
            if self.interrupt.is_set():
                break

        self.update_db()
        log.debug('ProxyTest update thread shutdown.')


class CleanupThread(Thread):
    def __init__(self, db_queue) -> None:
        Thread.__init__(self, name='cleanup', daemon=False)
        self.db_queue = db_queue
        self.args = db_queue.args
        self.interrupt = db_queue.interrupt

    def unlock_stuck(self):
        try:
            row_count = Proxy.unlock_stuck()
            if row_count > 0:
                log.debug(f'Unlocked {row_count} proxies stuck in testing.')
            return True
        except DatabaseError as e:
            log.warning(f'Failed to delete broken proxies: {e}')

        return False

    def update_db(self):
        try:
            Proxy.database().connect()

            self.unlock_stuck()

            row_count = Proxy.delete_failed(
                age_days=self.args.cleanup_age,
                test_count=self.args.cleanup_test_count,
                fail_ratio=self.args.cleanup_fail_ratio,
                limit=100)
            if row_count > 0:
                log.debug(f'Deleted {row_count} broken proxies.')
            return True
        except DatabaseError as e:
            log.warning(f'Failed to delete broken proxies: {e}')
        except MaxConnectionsExceeded as e:
            log.warning(f'Failed to acquire a database connection: {e}')
        finally:
            Proxy.database().close()

        return False

    def run(self) -> None:
        log.debug('Cleanup thread started.')
        error_count = 0
        while True:
            if error_count > 4:
                log.error('Unable to cleanup database.')
                self.interrupt.set()
                break

            if self.interrupt.is_set():
                break

            if not self.db_queue.lock_database():
                time.sleep(1.0)
                continue

            result = self.update_db()
            self.db_queue.unlock_database()

            if not result:
                error_count += 1
                time.sleep(1.0 * error_count)
                continue

            error_count = 0
            time.sleep(30.0)

        log.debug('Cleanup thread shutdown.')


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

        self.insert_proxy_thread = InsertProxyThread(self)
        self.testing_thread = TestingThread(self)
        self.update_proxy_thread = UpdateProxyThread(self, 10)
        self.update_proxytest_thread = UpdateProxyTestThread(self, 10)
        self.cleanup_thread = CleanupThread(self)

    def start(self):
        """
        Start database queue threads.
        Note: thread calling this method needs to remain alive.
        """
        self.insert_proxy_thread.start()
        self.testing_thread.start()
        self.update_proxy_thread.start()
        self.update_proxytest_thread.start()
        self.cleanup_thread.start()

    def stop(self):
        self.interrupt.set()
        log.info('Waiting for queue threads to finish...')
        self.insert_proxy_thread.join()
        self.testing_thread.join()
        self.update_proxy_thread.join()
        self.update_proxytest_thread.join()
        self.cleanup_thread.join()
        log.info('Database queue threads shutdown.')

    def lock_database(self):
        try:
            DBConfig.database().connect(reuse_if_open=True)
            return DBConfig.lock_database(self.args.local_ip)
        except DatabaseError as e:
            log.error(f'Failed to lock database: {e}')
        except MaxConnectionsExceeded as e:
            log.error(f'Failed to acquire a database connection: {e}')
        finally:
            ProxyTest.database().close()
        return False

    def unlock_database(self):
        try:
            DBConfig.database().connect(reuse_if_open=True)
            return DBConfig.unlock_database(self.args.local_ip)
        except DatabaseError as e:
            log.error(f'Failed to unlock database: {e}')
        except MaxConnectionsExceeded as e:
            log.error(f'Failed to acquire a database connection: {e}')
        finally:
            ProxyTest.database().close()
        return False

    def insert_proxylist(self, proxylist):
        self.insert_proxy_thread.put_list(proxylist)

    def get_proxy(self):
        return self.testing_thread.get_proxy()

    def update_proxy(self, proxy):
        self.update_proxy_thread.put(proxy)

    def update_proxytest(self, proxytest):
        self.update_proxytest_thread.put(proxytest)

    def print_stats(self):
        self.testing_thread.print_stats()
        self.insert_proxy_thread.print_stats()
        self.update_proxy_thread.print_stats()
        self.update_proxytest_thread.print_stats()
