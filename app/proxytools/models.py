#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

from peewee import (
    fn, JOIN, Case, OperationalError, IntegrityError,
    Model, ModelSelect, ModelUpdate, ModelDelete,
    ForeignKeyField, BigAutoField, DateTimeField, CharField,
    IntegerField, BigIntegerField, SmallIntegerField, IPField)

from datetime import datetime, timedelta
from enum import IntEnum
from hashlib import blake2b

log = logging.getLogger(__name__)


class ProxyProtocol(IntEnum):
    HTTP = 0
    SOCKS4 = 1
    SOCKS5 = 2


class ProxyStatus(IntEnum):
    UNKNOWN = 0
    TESTING = 1
    OK = 2
    TIMEOUT = 3
    ERROR = 4
    BANNED = 5


###############################################################################
# Custom field types
# https://docs.peewee-orm.com/en/latest/peewee/models.html#field-types-table
###############################################################################
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
class IntEnumField(SmallIntegerField):
    """	Unsigned integer representation field for Enum """
    field_type = 'smallint unsigned'

    def __init__(self, choices, *args, **kwargs):
        super(SmallIntegerField, self).__init__(*args, **kwargs)
        self.choices = choices

    def db_value(self, value):
        return value.value

    def python_value(self, value):
        return self.choices(value)


###############################################################################
# Database models
# https://docs.peewee-orm.com/en/latest/peewee/models.html#model-options-and-table-metadata
# https://docs.peewee-orm.com/en/latest/peewee/models.html#meta-primary-key
# https://docs.peewee-orm.com/en/latest/peewee/models.html#field-initialization-arguments
# Note: field attribute "default" is implemented purely in Python and "choices" are not validated.
###############################################################################
class BaseModel(Model):
    @classmethod
    def database(cls):
        return cls._meta.database

    @classmethod
    def get_all(cls):
        return [m for m in cls.select().dicts()]

    @classmethod
    def get_random(cls, limit=1):
        return cls.select().order_by(fn.Rand()).limit(limit)


class Proxy(BaseModel):
    id = BigAutoField()
    ip = IPField()
    port = USmallIntegerField()
    protocol = IntEnumField(ProxyProtocol, index=True)
    username = Utf8mb4CharField(null=True, max_length=32)
    password = Utf8mb4CharField(null=True, max_length=32)
    status = IntEnumField(ProxyStatus, index=True, default=ProxyStatus.UNKNOWN)
    latency = UIntegerField(index=True, default=0)  # milliseconds
    test_count = UIntegerField(index=True, default=0)
    fail_count = UIntegerField(index=True, default=0)
    country = Utf8mb4CharField(index=True, null=True, max_length=2)
    created = DateTimeField(index=True, default=datetime.utcnow)
    modified = DateTimeField(index=True, default=datetime.utcnow)

    class Meta:
        indexes = (
            # create a unique on ip/port
            (('ip', 'port'), True),
        )

    def test_score(self) -> float:
        """ Success rate """
        if self.test_count:
            return (1.0 - self.fail_count / self.test_count) * 100
        return 0.0

    def __repr__(self):
        return f'{self.ip}:{self.port}'

    def data(self) -> dict:
        return {
            'id': self.id,
            'url': self.url(),
            'ip': self.ip,
            'port': self.port,
            'protocol': ProxyProtocol(self.protocol).name,
            'username': self.username,
            'password': self.password,
            'status': ProxyStatus(self.status).name,
            'latency': self.latency,
            'test_count': self.test_count,
            'fail_count': self.fail_count,
            'score': self.test_score(),
            'country': self.country,
            'created': self.created,
            'modified': self.modified,
        }

    def url(self, no_protocol=False) -> str:
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

    def url_proxychains(self):
        """
        Build a proxychains URL string from proxy data.
        Format: socks5 192.168.67.78 1080 lamer secret

        Returns:
            string: ProxyChains formatted proxy URL
        """
        url = f"{self.ip} {self.port}"
        if self.username and self.password:
            url = f"{url} {self.username} {self.password}"

        protocol = self.protocol.name.lower()
        url = f"{protocol} {url}"

        return url

    @staticmethod
    def latest_tests(limit=1000) -> ModelSelect:
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

    def need_scan(limit=1000, age_secs=3600, protocols=[]):
        min_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = (
            (Proxy.modified < min_age) &
            (Proxy.status != ProxyStatus.TESTING))

        if protocols:
            conditions &= (Proxy.protocol << protocols)

        query = (Proxy
                 .select(Proxy)
                 .where(conditions)
                 .order_by(Proxy.status.asc(),  # lower status status
                           Proxy.modified.asc())  # older records first
                 .limit(limit))

        return query

    def get_for_scan(age_secs=3600, protocols=[]):
        min_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = (
            ((Proxy.status == ProxyStatus.UNKNOWN) | (
                (Proxy.modified < min_age) &
                (Proxy.status != ProxyStatus.TESTING))))

        if protocols:
            conditions &= (Proxy.protocol << protocols)

        query = (Proxy
                 .select(Proxy)
                 .where(conditions)
                 .order_by(fn.Rand()))  # random sort to mitigate row locking

        return query.first()

    def lock_for_testing(self):
        """
        Lock proxy status in testing.
        Record is updated only if proxy still holds its previous state.
        """
        conditions = (
            (Proxy.id == self.id) &
            (Proxy.status == self.status))

        query = (Proxy
                 .update(status=ProxyStatus.TESTING, modified=datetime.utcnow())
                 .where(conditions))

        return query.execute()

    def unlock(self):
        """
        Unlock proxy from testing status.
        """
        proxy_test = self.latest_test()

        query = (Proxy
                 .update(status=proxy_test.status, modified=proxy_test.created)
                 .where(Proxy.id == self.id))

        return query.execute()

    @staticmethod
    def bulk_lock(proxy_ids):
        """
        Lock proxies to testing status.
        """

        query = (Proxy
                 .update(status=ProxyStatus.TESTING, modified=datetime.utcnow())
                 .where(Proxy.id << proxy_ids))

        return query.execute()

    @staticmethod
    def bulk_unlock(proxy_ids):
        """
        Unlock proxies from testing status.
        """

        query = (Proxy
                 .update(status=ProxyStatus.UNKNOWN)
                 .where(Proxy.id << proxy_ids))

        return query.execute()

    def test_stats(self, age_days=0) -> tuple:
        """
        Select total number of tests done and failed.

        Args:
            age_days (int, optional): Maximum test age. Defaults to 0 (all).

        Returns:
            tuple: test_count, fail_count
        """
        conditions = ((ProxyTest.proxy == self.id))

        if age_days > 0:
            max_age = datetime.utcnow() - timedelta(days=age_days)
            conditions &= ((ProxyTest.created > max_age))

        fail_count = fn.SUM(Case(None, [(ProxyTest.status == ProxyStatus.OK, 0)], 1))
        query = (ProxyTest
                 .select(
                    fn.COUNT(ProxyTest.id),
                    fail_count)
                 .where(conditions))

        return query.scalar(as_tuple=True)

    def latest_test(self):
        query = (ProxyTest
                 .select()
                 .where(ProxyTest.proxy == self.id)
                 .order_by(ProxyTest.id.desc()))
        return query.first()

    def latest_test_id(self):
        """ Retrieve the latest test ID performed. """
        query = (ProxyTest
                 .select(fn.MAX(ProxyTest.id))
                 .where(ProxyTest.proxy == self.id))
        return query

    def oldest_test(self):
        """ Retrieve the oldest test performed. """
        query = (ProxyTest
                 .select()
                 .where(ProxyTest.proxy == self.id)
                 .order_by(ProxyTest.id.asc()))
        return query.first()

    def oldest_test_id(self):
        """ Retrieve the oldest test ID performed. """
        query = (ProxyTest
                 .select(fn.MIN(ProxyTest.id))
                 .where(ProxyTest.proxy == self.id))
        return query

    @staticmethod
    def get_valid(limit=1000, age_secs=3600, protocol=None, exclude_countries=[]):
        """
        Get a list of valid proxies tested recently.

        Args:
            limit (int, optional): Defaults to 1000.
            age_secs (int, optional): Maximum test age. Defaults to 3600 secs.
            protocol (ProxyProtocol, optional): Filter by protocol. Defaults to None.

        Returns:
            query: Proxies that have been validated.
        """
        min_age = datetime.utcnow() - timedelta(seconds=age_secs)
        conditions = (
            (Proxy.modified > min_age) &
            (Proxy.status == ProxyStatus.OK))

        if protocol:
            conditions &= (Proxy.protocol == protocol)

        if exclude_countries:
            conditions &= (Proxy.country.not_in(exclude_countries))

        query = (Proxy
                 .select()
                 .where(conditions)
                 .order_by(Proxy.created.asc())  # get older first
                 .limit(limit))

        return query

    # https://docs.peewee-orm.com/en/latest/peewee/querying.html#inserting-rows-in-batches
    @staticmethod
    def bulk_insert(proxylist, batch_size=250):
        """
        Insert new proxies to the database.

        Args:
            proxylist (list[{proxy}, ...]): list of proxy formatted dictionary

        Returns:
            int count: inserted proxy count
        """
        log.info('Processing %d proxies into the database.', len(proxylist))
        count = 0
        with Proxy.database().atomic():
            for idx in range(0, len(proxylist), batch_size):
                batch = proxylist[idx:idx + batch_size]
                try:
                    query = (Proxy
                             .insert_many(batch)
                             .on_conflict(preserve=[
                                    Proxy.username,
                                    Proxy.password,
                                    Proxy.protocol,
                                    Proxy.modified
                                ]))
                    if query.execute():
                        count += len(batch)
                except IntegrityError as e:
                    log.exception('Unable to insert proxies: %s', e)
                except OperationalError as e:
                    log.exception('Failed to insert proxies: %s', e)

        return count

    @staticmethod
    def unlock_stuck(age_minutes=60) -> ModelUpdate:
        """
        Unlock proxies stuck in testing for too long.

        Args:
            age_minutes (int, optional): Maximum test time. Defaults to 15 minutes.

        Returns:
            query: Update query
        """
        min_age = datetime.utcnow() - timedelta(minutes=age_minutes)
        conditions = (
            (Proxy.modified < min_age) &
            (Proxy.status == ProxyStatus.TESTING))

        query = (Proxy
                 .update(status=ProxyStatus.ERROR, modified=datetime.utcnow())
                 .where(conditions))

        return query.execute()

    def get_failed(age_days=14, test_count=20, fail_days=7, fail_count=10) -> ModelDelete:
        """
        Select old proxies with no success tests.

        Args:
            age_days (int, optional): Minimum proxy age. Defaults to 14 days.
            test_count (int, optional): Minimum number of attempts made. Defaults to 20.
            fail_days (int, optional): Period of testing to analyse. Defaults to 7 days.
            fail_count (int, optional): Minimum number of failures during period. Defaults to 10.

        Returns:
            query: Delete query
        """
        min_age = datetime.utcnow() - timedelta(days=age_days)
        fail_age = datetime.utcnow() - timedelta(days=fail_days)

        conditions = (
            (Proxy.created < min_age) &
            (Proxy.test_count > test_count) &
            (ProxyTest.created < fail_age) &
            (ProxyTest.status != ProxyStatus.OK))

        query = (Proxy
                 .select(Proxy, fn.Count(ProxyTest.id).alias('count'))
                 .join(ProxyTest, JOIN.LEFT_OUTER)
                 .where(conditions)
                 .group_by(Proxy)
                 .having(fn.Count(ProxyTest.id) > fail_count))

        return query

    @staticmethod
    def delete_failed(age_days=14, test_count=20, fail_rate=0.9, limit=100):
        """
        Delete old proxies with no success tests.

        Args:
            age_days (int, optional): Minimum proxy age. Defaults to 14 days.
            test_count (int, optional): Minimum number of attempts made. Defaults to 20.
            fail_rate (float, optional): Failure rate to delete. Defaults to 0.9 (90%).
            limit (int, optional): Maximum number of records deleted.

        Returns:
            query: Deleted proxy count
        """
        min_age = datetime.utcnow() - timedelta(days=age_days)

        conditions = (
            (Proxy.status != ProxyStatus.TESTING) &
            (Proxy.created < min_age) &
            (Proxy.test_count > test_count) &
            (Proxy.fail_count / Proxy.test_count > fail_rate))

        query = (Proxy
                 .delete()
                 .where(conditions)
                 .limit(limit))

        return query.execute()


class ProxyTest(BaseModel):
    id = BigAutoField()
    # Note: we can use deferred FK if circular reference in Proxy
    proxy = ForeignKeyField(Proxy, backref='tests', on_delete='CASCADE')
    status = IntEnumField(ProxyStatus, index=True, default=ProxyStatus.UNKNOWN)
    latency = UIntegerField(index=True, default=0)
    info = Utf8mb4CharField(null=True)
    created = DateTimeField(index=True, default=datetime.utcnow)

    def __repr__(self):
        return f'{self.proxy}-{self.status}'

    @staticmethod
    def latest(exclude_ids=[]):
        """ Retrieve latest tests """
        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MAX(ProxyTest.id))
                 .where(ProxyTest.proxy.not_in(exclude_ids))
                 .group_by(ProxyTest.proxy))
        return query

    @staticmethod
    def oldest(exclude_ids=[]):
        """ Retrieve oldest tests """
        query = (ProxyTest
                 .select(ProxyTest.proxy, fn.MIN(ProxyTest.id))
                 .where(ProxyTest.proxy.not_in(exclude_ids))
                 .group_by(ProxyTest.proxy))
        return query

    @staticmethod
    def latest_test(proxy_id):
        """ Retrieve the latest test ID performed on `proxy_id` """
        query = (ProxyTest
                 .select(fn.MAX(ProxyTest.id))
                 .where(ProxyTest.proxy == proxy_id))
        return query

    @staticmethod
    def oldest_test(proxy_id):
        """ Retrieve the oldest test ID performed on `proxy_id` """
        query = (ProxyTest
                 .select(fn.MIN(ProxyTest.id))
                 .where(ProxyTest.proxy == proxy_id))
        return query

    @staticmethod
    def all_tests(proxy_id, age_days=14) -> ModelSelect:
        """ Count the number of tests performed on `proxy_id`"""

        max_age = datetime.utcnow() - timedelta(days=age_days)

        conditions = (
            (ProxyTest.proxy == proxy_id) &
            (ProxyTest.created > max_age))

        query = (ProxyTest
                 .select()
                 .where(conditions))

        return query

    @staticmethod
    def failed_tests(proxy_id, age_days=14) -> ModelSelect:
        """ Count the number of tests failed on `proxy_id`"""

        max_age = datetime.utcnow() - timedelta(days=age_days)

        conditions = (
            (ProxyTest.proxy == proxy_id) &
            (ProxyTest.created > max_age) &
            (ProxyTest.status != ProxyStatus.OK))

        query = (ProxyTest
                 .select()
                 .where(conditions))

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
                 .select(ProxyTest)
                 .where(conditions))
        return query


class DBConfig(BaseModel):
    """ Database versioning model """
    key = Utf8mb4CharField(null=False, max_length=64, unique=True)
    val = Utf8mb4CharField(null=True, max_length=64)
    modified = DateTimeField(index=True, default=datetime.utcnow)

    class Meta:
        primary_key = False
        table_name = 'db_config'

    @staticmethod
    def get_schema_version() -> int:
        """ Get current schema version """
        db_ver = DBConfig.get(DBConfig.key == 'schema_version').val
        return int(db_ver)

    @staticmethod
    def insert_schema_version(schema_version):
        """ Insert current schema version """
        DBConfig.insert(
            key='schema_version',
            val=schema_version
        ).execute()

    @staticmethod
    def update_schema_version(schema_version):
        """ Update current schema version """
        with DBConfig.database().atomic():
            query = (DBConfig
                     .update(val=schema_version)
                     .where(DBConfig.key == 'schema_version'))
            query.execute()

    @staticmethod
    def init_lock():
        """ Initialize database lock """
        DBConfig.get_or_create(
            key='read_lock',
            defaults={'val': None})

    @staticmethod
    def lock_database(local_ip):
        """ Update database lock with local IP """
        hash = blake2b(local_ip.encode(), digest_size=10).hexdigest()

        conditions = (
            (DBConfig.key == 'read_lock') &
            (DBConfig.val.is_null(True)))

        query = (DBConfig
                 .update(val=hash, modified=datetime.utcnow())
                 .where(conditions))
        row_count = query.execute()

        if row_count == 1:
            return True

        max_lock = datetime.utcnow() - timedelta(seconds=10)
        conditions = (
            (DBConfig.key == 'read_lock') &
            (DBConfig.modified < max_lock))

        query = (DBConfig
                 .update(val=hash, modified=datetime.utcnow())
                 .where(conditions))

        row_count = query.execute()
        if row_count == 1:
            log.warning('Database locked forcibly.')
            return True

        return False

    @staticmethod
    def unlock_database(local_ip):
        """ Update database to clear lock """
        hash = blake2b(local_ip.encode(), digest_size=10).hexdigest()

        conditions = (
            (DBConfig.key == 'read_lock') &
            (DBConfig.val == hash))

        query = (DBConfig
                 .update(val=None, modified=datetime.utcnow())
                 .where(conditions))
        row_count = query.execute()

        if row_count == 1:
            return True

        log.warning('Failed to unlock database.')
        return False
