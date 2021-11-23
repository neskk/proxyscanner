#!/usr/bin/python
# -*- coding: utf-8 -*-

import hashlib
import logging
import socket
import struct
import sys

from peewee import *
from playhouse.pool import PooledMySQLDatabase
from playhouse.migrate import migrate, MySQLMigrator

from datetime import datetime, timedelta
from enum import IntEnum

from .utils import ip2int, int2ip


log = logging.getLogger(__name__)

# https://docs.peewee-orm.com/en/latest/peewee/database.html#dynamically-defining-a-database
# https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#database-url
db = DatabaseProxy()
db_schema_version = 1
db_step = 250

#db = SqliteDatabase('sqlite-debug.db')


def init_database(db_name, db_host, db_port, db_user, db_pass):
    """ Create a pooled connection to MySQL database """
    log.info('Connecting to MySQL database on %s:%i...', db_host, db_port)

    database = PooledMySQLDatabase(
        db_name,
        user=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        stale_timeout=60,
        max_connections=None,
        charset='utf8mb4')

    # Initialize DatabaseProxy
    db.initialize(database)

    try:
        verify_database_schema()
        verify_table_encoding(db_name)
    except Exception as e:
        log.exception('Failed to verify database schema: %s', e)
        sys.exit(1)
    return db

# Enum Classes
class ProxyProtocol(IntEnum):
    HTTP = 0
    SOCKS4 = 1
    SOCKS5 = 2


class ProxyStatus(IntEnum):
    OK = 0
    UNKNOWN = 1
    ERROR = 2
    TIMEOUT = 3
    BANNED = 4


# https://docs.peewee-orm.com/en/latest/peewee/models.html#field-types-table
# Custom field types
class Utf8mb4CharField(CharField):
    def __init__(self, max_length=191, *args, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)


class UBigIntegerField(BigIntegerField):
    field_type = 'bigint unsigned'


class UIntegerField(IntegerField):
    field_type = 'int unsigned'


class USmallIntegerField(SmallIntegerField):
    field_type = 'smallint unsigned'


# https://github.com/coleifer/peewee/issues/630
class EnumField(SmallIntegerField):
    """	Integer representation field for Enum """
    def __init__(self, choices, *args, **kwargs):
        super(SmallIntegerField, self).__init__(*args, **kwargs)
        self.choices = choices

    def db_value(self, value):
        return value.value

    def python_value(self, value):
        return self.choices(value)


# https://docs.peewee-orm.com/en/latest/peewee/models.html#model-options-and-table-metadata
# https://docs.peewee-orm.com/en/latest/peewee/models.html#meta-primary-key
class BaseModel(Model):
    class Meta:
        database = db

    @classmethod
    def database(cls):
        return cls._meta.database

    @classmethod
    def get_all(cls):
        return [m for m in cls.select().dicts()]



class ProxyTest(BaseModel):
    id = BigAutoField()
    proxy = DeferredForeignKey('Proxy', backref='tests')
    latency = UIntegerField(index=True, null=True)
    status = USmallIntegerField(index=True, default=ProxyStatus.UNKNOWN)
    info = Utf8mb4CharField(null=True)
    created = DateTimeField(index=True, default=datetime.utcnow)

    @staticmethod
    def latest():
        query = (ProxyTest
         .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
         .group_by(ProxyTest.proxy))

        return query

    @staticmethod
    def valid(age_secs=3600, exclude_ids=[]):
        """
        Retrieve proxies with the latest valid tests.

        Args:
            age_secs (int, optional): Maximum test age. Defaults to 3600 secs.
            exclude_ids (list, optional): Ignore these proxy IDs. Defaults to [].

        Returns:
            query: [(proxy_id, proxytest_id), ...]
        """

        max_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = ((ProxyTest.created > max_age) &
                      (ProxyTest.status == ProxyStatus.OK))

        if exclude_ids:
            conditions &= (ProxyTest.proxy.not_in(exclude_ids))

        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
                 .where(conditions)
                 .group_by(ProxyTest.proxy))
        return query


    @staticmethod
    def retest(age_secs=3600, exclude_ids=[], statuses=[ProxyStatus.UNKNOWN, ProxyStatus.ERROR, ProxyStatus.TIMEOUT]):
        """
        Retrieve proxies that require a new test.

        BROKEN: this gives me the last invalid, does not say the last test was invalid.

        Args:
            age_secs (int, optional): Minimum cooldown time. Defaults to 3600 secs.
            exclude_ids (list, optional): Ignore these proxy IDs. Defaults to [].
            statuses (list, optional): Defaults to [ProxyStatus.UNKNOWN, ProxyStatus.ERROR, ProxyStatus.TIMEOUT].

        Returns:
            query: [(proxy_id, proxytest_id), ...]
        """

        min_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = ((ProxyTest.created < min_age) &
                      (ProxyTest.status << statuses))

        if exclude_ids:
            conditions &= (ProxyTest.proxy.not_in(exclude_ids))

        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
                 .where(conditions)
                 .group_by(ProxyTest.proxy))
        return query

    @staticmethod
    def latest_tests(statuses=[]):
        """ Retrieve proxies latest tests """
        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
                 .where(ProxyTest.status << statuses)
                 .group_by(ProxyTest.proxy))
        return query

    @staticmethod
    def oldest_tests():
        """ Retrieve proxies oldest tests """
        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MIN(ProxyTest.id))
                 .group_by(ProxyTest.proxy))
        return query

    @staticmethod
    def latest_test(proxy_id):
        """ Retrieve the latest test performed on `proxy_id` """
        query = (ProxyTest
                 .select(fn.MAX(ProxyTest.id))
                 .where(ProxyTest.proxy == proxy_id))
        return query

    @staticmethod
    def oldest_test(proxy_id):
        """ Retrieve the oldest test performed on `proxy_id` """
        query = (ProxyTest
                 .select(fn.MIN(ProxyTest.id))
                 .where(ProxyTest.proxy == proxy_id))
        return query

    @staticmethod
    def delete_old(age_days=365):
        """
        Delete old proxy tests.

        Args:
            age_days (int, optional): Maximum test age. Defaults to 365 days.

        Returns:
            query: Delete query
        """
        max_age = datetime.utcnow() - timedelta(days=age_days)
        conditions = (ProxyTest.created > max_age)

        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
                 .where(conditions)
                 .group_by(ProxyTest.proxy))
        return query
        """
        rows = 0
        try:
            with db:
                query = (Proxy
                         .delete()
                         .where(Proxy.fail_count >= 5))
                rows = query.execute()
        except OperationalError as e:
            log.exception('Failed to delete failed proxies: %s', e)

        log.info('Deleted %d failed proxies from database.', rows)
        """


class Proxy(BaseModel):
    id = BigAutoField()
    ip = IPField()
    port = USmallIntegerField()
    protocol = USmallIntegerField(index=True)
    username = Utf8mb4CharField(null=True, max_length=32)
    password = Utf8mb4CharField(null=True, max_length=32)
    created = DateTimeField(index=True, default=datetime.utcnow)
    modified = DateTimeField(index=True, default=datetime.utcnow)

    class Meta:
        indexes = (
            # create a unique on ip/port
            (('ip', 'port'), True),
        )

    def url(self, no_protocol=False):
        """
        Build a URL string from proxy data.

        Args:
            no_protocol (bool, optional): Output URL without protocol. Defaults to False.

        Returns:
            string: Proxy URL
        """
        url = f"{self.ip}:{self.port}"

        if self.username and self.password:
            url = f"{self.username}:{self.password}@{url}"

        if not no_protocol:
            protocol = ProxyProtocol(self.protocol).name.lower()
            url = f"{protocol}://{url}"

        return url

    @staticmethod
    def url_format(proxy, no_protocol=False):
        """
        Build a URL string from proxy data.

        Args:
            proxy (dict): Proxy information.
            no_protocol (bool, optional): Output URL without protocol. Defaults to False.

        Returns:
            string: Proxy URL
        """
        proxy_url = '{}:{}'.format(proxy['ip'], proxy['port'])
        if proxy['username']:
            proxy_url = '{}:{}@{}'.format(
                proxy['username'], proxy['password'], proxy_url)

        if not no_protocol:
            if proxy['protocol'] == ProxyProtocol.HTTP:
                protocol = 'http'
            elif proxy['protocol'] == ProxyProtocol.SOCKS4:
                protocol = 'socks4'
            else:
                protocol = 'socks5'

            proxy_url = '{}://{}'.format(protocol, proxy_url)

        return proxy_url

    @staticmethod
    def url_format_proxychains(proxy):
        """
        Build a proxychains URL string from proxy data.
        Format: socks5 192.168.67.78 1080 lamer secret

        Args:
            proxy (dict): Proxy information.

        Returns:
            string: Proxy URL
        """
        url = f"{proxy['ip']} {proxy['port']}"
        if proxy['username'] and proxy['password']:
            url = f"{url} {proxy['username']} {proxy['password']}"

        protocol = proxy['protocol'].name.lower()
        url = f"{protocol} {url}"

        return url

    @staticmethod
    def latest_tests(limit=1000):
        """
        Latest tested proxies using a join query.

        Returns:
            query: Proxy model query.
        """
        ProxyTestAlias = ProxyTest.alias()

        subquery = (ProxyTestAlias
                    .select(fn.MAX(ProxyTestAlias.id))
                    .where(ProxyTestAlias.proxy == Proxy.id)
                    .limit(limit))

        query = (Proxy
                 .select(Proxy, ProxyTest)
                 .join(ProxyTest)
                 .where(ProxyTest.id == subquery))

        return query

    @staticmethod
    def untested(limit=1000, exclude_ids=[], protocol=None):
        """
        Get a list of untested proxies.

        Used query:
        SELECT id FROM A WHERE id NOT IN (SELECT id FROM B)

        Alternative queries:
        SELECT id FROM A WHERE NOT EXISTS (SELECT * FROM B WHERE B.id=A.id)
        SELECT id FROM A LEFT JOIN B ON A.id=B.id WHERE B.id IS NULL

        Args:
            limit (int, optional): Defaults to 1000.
            exclude_ids (list, optional): Ignore these proxy IDs. Defaults to [].
            protocol (ProxyProtocol, optional): Filter by protocol. Defaults to None.

        Returns:
            query: Proxy models that have not been tested.
        """
        conditions = (Proxy.id.not_in(ProxyTest.select(ProxyTest.proxy)))

        if exclude_ids:
            conditions &= (Proxy.id.not_in(exclude_ids))

        if protocol is not None:
            conditions &= (Proxy.protocol == protocol)

        query = (Proxy
                 .select(Proxy)
                 .where(conditions)
                 .order_by(Proxy.created.asc())  # get older first
                 .limit(limit))

        return query

    @staticmethod
    def valid(limit=1000, age_secs=3600, exclude_ids=[], protocol=None):
        """
        Get a list of valid tested proxies.

        Args:
            limit (int, optional): Defaults to 1000.
            age_secs (int, optional): Maximum test age. Defaults to 3600 secs.
            exclude_ids (list, optional): Ignore these proxy IDs. Defaults to [].
            protocol (ProxyProtocol, optional): Filter by protocol. Defaults to None.

        Returns:
            query: Proxies that have been validated.
        """
        subquery = ProxyTest.valid(age_secs, exclude_ids)
        res = subquery.tuples().execute()
        proxy_ids = []
        if res.count > 0:
            proxy_ids, _ = zip(*res)

        conditions = (Proxy.id.in_(proxy_ids))

        if exclude_ids:
            conditions &= (Proxy.id.not_in(exclude_ids))

        if protocol is not None:
            conditions &= (Proxy.protocol == protocol)

        query = (Proxy
                .select(Proxy)
                .where(conditions)
                .order_by(Proxy.created.asc())  # get older first
                .limit(limit))

        return query


    @staticmethod
    def retest(limit=1000, exclude_ids=[], age_secs=3600, protocol=None):
        """
        Get a list of proxies that require testing.

        Args:
            limit (int, optional): Defaults to 1000.
            age_secs (int, optional): Maximum test age. Defaults to 3600 secs.
            exclude_ids (list, optional): Ignore these proxy IDs. Defaults to [].
            protocol (ProxyProtocol, optional): Filter by protocol. Defaults to None.

        Returns:
            query: Proxies that need to be retested.
        """
        subquery = ProxyTest.retest(age_secs, exclude_ids)
        res = subquery.tuples().execute()
        log.debug("Subquery res: %s", res)
        proxy_ids = []
        if res.count > 0:
            proxy_ids, _ = zip(*res)
            log.debug("Proxy IDs: %s", proxy_ids)

        conditions = (Proxy.id.in_(proxy_ids))

        if exclude_ids:
            conditions &= (Proxy.id.not_in(exclude_ids))

        if protocol is not None:
            conditions &= (Proxy.protocol == protocol)

        query = (Proxy
                .select(Proxy)
                .where(conditions)
                .order_by(Proxy.created.asc())  # get older first
                .limit(limit))

        return query

    # https://docs.peewee-orm.com/en/latest/peewee/querying.html#inserting-rows-in-batches
    @staticmethod
    def insert_bulk(proxylist):
        """
        Insert new proxies to the database.

        Args:
            proxylist (list[{proxy}, ...]): list of proxy formatted dictionary

        Returns:
            int count: inserted proxy count
        """
        log.info('Processing %d proxies into the database.', len(proxylist))
        count = 0
        for idx in range(0, len(proxylist), db_step):
            batch = proxylist[idx:idx + db_step]
            try:
                with db.atomic():
                    query = (Proxy
                        .insert_many(batch)
                        .on_conflict(
                            preserve=[
                                Proxy.username,
                                Proxy.password,
                                Proxy.protocol,
                                Proxy.modified
                            ]
                        ))
                    if query.execute():
                        count += len(batch)
            except IntegrityError as e:
                log.exception('Unable to insert new proxies: %s', e)
            except OperationalError as e:
                log.exception('Failed to insert new proxies: %s', e)

        log.info('Inserted %d new proxies into the database.', count)
        return count


class Version(BaseModel):
    """ Database versioning model """
    key = Utf8mb4CharField()
    val = SmallIntegerField()

    class Meta:
        primary_key = False

MODELS = [Proxy, ProxyTest, Version]

def create_tables():
    """ Create tables in the database (skips existing) """
    with db:
        for table in MODELS:
            if not table.table_exists():
                log.info('Creating database table: %s', table.__name__)
                db.create_tables([table], safe=True)
            else:
                log.debug('Skipping database table %s, it already exists.',
                          table.__name__)


def drop_tables():
    """ Drop all the tables in the database """
    with db:
        db.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
        for table in MODELS:
            if table.table_exists():
                log.info('Dropping database table: %s', table.__name__)
                db.drop_tables([table], safe=True)

        db.execute_sql('SET FOREIGN_KEY_CHECKS=1;')


# https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#schema-migrations
def migrate_database_schema(old_ver):
    """ Migrate database schema """
    log.info('Detected database version %i, updating to %i...',
             old_ver, db_schema_version)

    with db:
        # Update database schema version
        query = (Version
                 .update(val=db_schema_version)
                 .where(Version.key == 'schema_version'))
        query.execute()

    # Perform migrations here
    migrator = MySQLMigrator(db)

    if old_ver < 2:
        # Remove hash field unique index
        migrate(migrator.drop_index('sample_model', 'sample_model_hash'))
        # Reset hash field in all rows
        Proxy.update(hash=1).execute()
        # Modify column type
        db.execute_sql(
            'ALTER TABLE `proxy` '
            'CHANGE COLUMN `hash` `hash` INT UNSIGNED NOT NULL;'
        )
        # Re-hash all proxies
        Proxy.rehash_all()
        # Recreate hash field unique index
        migrate(migrator.add_index('proxy', ('hash',), True))

    if old_ver < 3:
        # Add response time field
        migrate(
            migrator.add_column('proxy', 'latency',
                                UIntegerField(index=True, null=True))
        )

    # Always log that we're done.
    log.info('Schema upgrade complete.')
    return True


def verify_database_schema():
    """ Verify if database is properly initialized """
    if not Version.table_exists():
        log.info('Database schema is not created, initializing...')
        create_tables()
        Version.insert(key='schema_version', val=db_schema_version).execute()
    else:
        db_ver = Version.get(Version.key == 'schema_version').val

        if db_ver < db_schema_version:
            if not migrate_database_schema(db_ver):
                log.error('Error migrating database schema.')
                sys.exit(1)

        elif db_ver > db_schema_version:
            log.error('Your database version (%i) seems to be newer than '
                      'the code supports (%i).', db_ver, db_schema_version)
            log.error('Upgrade your code base or drop the database.')
            sys.exit(1)


def verify_table_encoding(db_name):
    """ Verify if table collation is valid """
    with db:
        cmd_sql = '''
            SELECT table_name FROM information_schema.tables WHERE
            table_collation != "utf8mb4_unicode_ci"
            AND table_schema = "%s";''' % db_name
        change_tables = db.execute_sql(cmd_sql)

        cmd_sql = 'SHOW tables;'
        tables = db.execute_sql(cmd_sql)

        if change_tables.rowcount > 0:
            log.info('Changing collation and charset on %s tables.',
                     change_tables.rowcount)

            if change_tables.rowcount == tables.rowcount:
                log.info('Changing whole database, this might a take while.')

            db.execute_sql('SET FOREIGN_KEY_CHECKS=0;')
            for table in change_tables:
                log.debug('Changing collation and charset on table %s.',
                          table[0])
                cmd_sql = '''
                    ALTER TABLE %s CONVERT TO CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;''' % str(table[0])
                db.execute_sql(cmd_sql)
            db.execute_sql('SET FOREIGN_KEY_CHECKS=1;')
