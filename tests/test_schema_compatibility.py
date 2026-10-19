"""Gate unit tests never contact a configured database."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock, patch

import mysql.connector
from flask import Flask
from schema_compatibility import inspect_schema, Inspection


class InspectorTests(unittest.TestCase):
    def test_unsupported_versions_and_wrong_database_short_circuit(self):
        for version, expected in [('8.0.15','synthetic'),('5.7.44','synthetic'),
                                  ('10.11.1-MariaDB','synthetic'),('not-a-version','synthetic'),
                                  ('8.0.46','wrong')]:
            with self.subTest(version=version, expected=expected):
                connection = MagicMock()
                cursor = connection.cursor.return_value.__enter__.return_value
                cursor.fetchone.return_value = dict(version=version,db='synthetic')
                self.assertFalse(inspect_schema(connection, expected).compatible)
                self.assertEqual(cursor.execute.call_count, 1)

    def test_metadata_errors_propagate(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = mysql.connector.Error('private SQL')
        with self.assertRaises(mysql.connector.Error): inspect_schema(connection, 'synthetic')


class ConnectionGateTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        self.stack.enter_context(patch.dict('os.environ', DB_HOST='synthetic', DB_PORT='3306',
            DB_USER='synthetic', DB_PASSWORD='synthetic', DB_NAME='synthetic'))
        self.database = importlib.import_module('database')
        self.database.invalidate_compatibility()
        self.addCleanup(self.database.invalidate_compatibility)
        self.connection = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('synthetic',)
        self.connect = self.stack.enter_context(patch('mysql.connector.connect', return_value=self.connection))
        self.inspect = self.stack.enter_context(patch.object(self.database, 'inspect_schema', return_value=Inspection(())))

    def test_lease_expiry_and_explicit_invalidation(self):
        with patch.object(self.database.time, 'monotonic', return_value=10) as clock:
            self.database.get_connection()
            self.database.get_connection()
            self.assertEqual(self.inspect.call_count, 1)
            clock.return_value = 12.01
            self.database.get_connection()
            self.assertEqual(self.inspect.call_count, 2)
            self.database.invalidate_compatibility()
            self.database.get_connection()
            self.assertEqual(self.inspect.call_count, 3)

    def test_negative_lease_blocks_then_expires(self):
        self.inspect.return_value = Inspection(('missing CHECK',))
        with patch.object(self.database.time, 'monotonic', return_value=10) as clock:
            for _ in range(2):
                with self.assertRaises(self.database.SchemaUnavailable): self.database.get_connection()
            self.assertEqual(self.inspect.call_count, 1)
            self.inspect.return_value = Inspection(())
            with self.assertRaises(self.database.SchemaUnavailable): self.database.get_connection()
            clock.return_value = 11.01
            self.database.get_connection()
            self.assertEqual(self.inspect.call_count, 2)

    def test_changed_configuration_invalidates_lease(self):
        self.database.get_connection()
        with patch.dict('os.environ', DB_USER='another'):
            self.database.get_connection()
        self.assertEqual(self.inspect.call_count, 2)

    def test_wrong_actual_database_rejected_even_with_lease(self):
        self.database.get_connection()
        self.connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('wrong',)
        with self.assertRaises(self.database.SchemaUnavailable): self.database.get_connection()
        self.connection.close.assert_called()

    def test_incompatible_closes_connection(self):
        self.inspect.return_value = Inspection(('private schema diagnostic',))
        with self.assertRaisesRegex(self.database.SchemaUnavailable, '^Database compatibility unavailable.$'):
            self.database.get_connection()
        self.connection.close.assert_called_once()

    def test_connection_and_metadata_errors_clear_lease(self):
        for target in (self.connect,self.inspect):
            self.database.invalidate_compatibility()
            target.side_effect = mysql.connector.Error('secret raw SQL')
            with self.assertRaises(self.database.SchemaUnavailable) as error:
                self.database.get_connection()
            self.assertNotIn('secret',str(error.exception))
            self.assertIsNone(self.database._lease)
            target.side_effect = None

    def test_cleanup_errors_remain_safe_and_fail_closed(self):
        self.connection.close.side_effect = mysql.connector.Error('private close error')
        with self.assertRaises(self.database.SchemaUnavailable): self.database.ensure_ready()
        self.inspect.return_value = Inspection(('missing CHECK',))
        self.database.invalidate_compatibility()
        with self.assertRaises(self.database.SchemaUnavailable): self.database.get_connection()

    def test_no_testing_or_environment_bypass(self):
        self.inspect.return_value = Inspection(('missing CHECK',))
        with patch.dict('os.environ', ERP_ENV='testing', SCHEMA_GATE_DISABLED='true'):
            with self.assertRaises(self.database.SchemaUnavailable): self.database.get_connection()


class HTTPGateTests(unittest.TestCase):
    def setUp(self):
        with patch('dotenv.load_dotenv', return_value=False):
            from schema_gate import init_schema_gate
            self.database = importlib.import_module('database')
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='synthetic',TESTING=True)
        init_schema_gate(self.app)
        self.handler = MagicMock(return_value='business')
        self.app.add_url_rule('/business','business',self.handler,methods=['GET','POST'])
        self.client = self.app.test_client()

    def test_unavailable_html_json_and_readiness(self):
        with patch.object(self.database,'ensure_ready',side_effect=self.database.SchemaUnavailable('private')):
            for method in ('get','post'):
                response = getattr(self.client,method)('/business')
                self.assertEqual(response.status_code,503)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                self.assertNotIn('private',response.get_data(as_text=True))
            self.assertEqual(self.client.get('/business',headers={'Accept':'application/json'}).json,{'error':'service_unavailable'})
            self.assertEqual(self.client.get('/health/ready').status_code,503)
            self.assertEqual(self.client.get('/health/live').status_code,200)
        self.handler.assert_not_called()

    def test_connection_failure_inside_handler_is_503(self):
        self.handler.side_effect = self.database.SchemaUnavailable('private')
        with patch.object(self.database,'ensure_ready'):
            self.assertEqual(self.client.get('/business').status_code,503)

    def test_compatible_handlers_and_readiness(self):
        with patch.object(self.database,'ensure_ready'):
            self.assertEqual(self.client.post('/business').status_code,200)
            self.assertEqual(self.client.get('/health/ready').status_code,200)
        self.handler.assert_called_once()


class OperatorDiagnosticsTests(unittest.TestCase):
    def test_exit_statuses_and_no_secret_output(self):
        import io
        from contextlib import redirect_stdout
        from scripts import check_schema_compatibility as cli
        arguments = ['check','--host','synthetic','--port','3306','--user','synthetic','--database','synthetic']
        for result, failure, status in ((Inspection(()),None,0),
                (Inspection(('Missing revision capability',)),None,1),
                (None,mysql.connector.Error('PRIVATE_PASSWORD SQL'),2)):
            with self.subTest(status=status), patch('sys.argv',arguments), patch.object(cli,'getpass',return_value='PRIVATE_PASSWORD'), patch('mysql.connector.connect') as connect, patch.object(cli,'inspect_schema',return_value=result):
                connect.side_effect = failure
                output = io.StringIO()
                with redirect_stdout(output): self.assertEqual(cli.main(),status)
                self.assertNotIn('PRIVATE_PASSWORD',output.getvalue())
                self.assertNotIn(' SQL',output.getvalue())


if __name__ == '__main__': unittest.main()
