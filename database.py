"""Configured business connections, guarded by a bounded schema capability lease."""
import hashlib
import os
import threading
import time

import mysql.connector
from dotenv import load_dotenv
from schema_compatibility import inspect_schema, MANIFEST_VERSION

load_dotenv()

# Fixed, non-configurable upper bound. No production/testing bypass exists.
COMPATIBILITY_TTL_SECONDS = 2.0
INCOMPATIBILITY_TTL_SECONDS = 1.0
_lock = threading.Lock()
_lease = None


class SchemaUnavailable(RuntimeError):
    """Safe public error: internal diagnostics belong in the operator tool."""


def connection_options():
    required = ('DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME')
    if any(not os.getenv(name) for name in required):
        invalidate_compatibility()
        raise SchemaUnavailable('Database compatibility unavailable.')
    try:
        return dict(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                    user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                    database=os.environ['DB_NAME'], connection_timeout=3,
                    read_timeout=5, write_timeout=5)
    except ValueError:
        raise SchemaUnavailable('Database compatibility unavailable.') from None


def invalidate_compatibility():
    global _lease
    with _lock:
        _lease = None


def _key(options):
    return (MANIFEST_VERSION, options['host'], options['port'], options['user'],
            options['database'], hashlib.sha256(options['password'].encode()).digest())


def _validate(connection, options):
    global _lease
    key = _key(options)
    with _lock:
        if _lease and _lease[0] == key and time.monotonic() < _lease[1]:
            if not _lease[2]:
                raise SchemaUnavailable('Database compatibility unavailable.')
            return
        _lease = None
        result = inspect_schema(connection, options['database'])
        connection.rollback()  # End metadata transaction before repository use.
        if not result.compatible:
            _lease = (key, time.monotonic() + INCOMPATIBILITY_TTL_SECONDS, False)
            raise SchemaUnavailable('Database compatibility unavailable.')
        _lease = (key, time.monotonic() + COMPATIBILITY_TTL_SECONDS, True)


def _close_after_failure(connection):
    if connection is not None:
        try:
            connection.close()
        except mysql.connector.Error:
            # Cleanup failure must not replace the safe original error.
            invalidate_compatibility()


def get_connection():
    """Never return an unchecked business connection. No DDL or grants."""
    connection = None
    try:
        options = connection_options()
        connection = mysql.connector.connect(**options)
        # Verify actual selection even when a metadata lease is reused.
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATABASE()')
            if cursor.fetchone()[0] != options['database']:
                invalidate_compatibility()
                raise SchemaUnavailable('Database compatibility unavailable.')
        connection.rollback()
        _validate(connection, options)
        return connection
    except SchemaUnavailable:
        _close_after_failure(connection)
        raise
    except (mysql.connector.Error, ValueError, OSError):
        invalidate_compatibility()
        _close_after_failure(connection)
        raise SchemaUnavailable('Database compatibility unavailable.') from None


def ensure_ready():
    # Also proves connectivity on cache hits. A failed connection clears the lease.
    connection = get_connection()
    try:
        connection.close()
    except mysql.connector.Error:
        invalidate_compatibility()
        raise SchemaUnavailable('Database compatibility unavailable.') from None
