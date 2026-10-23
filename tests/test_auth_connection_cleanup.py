"""Authentication read cleanup under connector faults, without database access."""
import unittest
from unittest.mock import MagicMock, patch
from mysql.connector import Error
import user_repository as repo


class AuthenticationConnectionCleanupTests(unittest.TestCase):
    def test_cursor_allocation_failures_close_held_connections(self):
        for function, value in ((repo.get_user_by_username, 'synthetic'), (repo.get_authorization_state, 1)):
            db = MagicMock(); db.cursor.side_effect = Error('synthetic allocation failure')
            with self.subTest(function=function.__name__), patch.object(repo, 'get_connection', return_value=db):
                with self.assertRaises(Error): function(value)
            db.close.assert_called_once()

    def test_cursor_close_failure_still_closes_connection_and_does_not_return_cached_auth(self):
        for function, value in ((repo.get_user_by_username, 'synthetic'), (repo.get_authorization_state, 1)):
            db = MagicMock(); cur = db.cursor.return_value
            cur.fetchall.return_value = []
            cur.close.side_effect = Error('synthetic close failure')
            with self.subTest(function=function.__name__), patch.object(repo, 'get_connection', return_value=db):
                with self.assertRaises(Error): function(value)
            db.close.assert_called_once()

    def test_query_failure_still_closes_both_resources(self):
        for function, value in ((repo.get_user_by_username, 'synthetic'), (repo.get_authorization_state, 1)):
            db = MagicMock(); cur = db.cursor.return_value
            cur.execute.side_effect = Error('synthetic query failure')
            with self.subTest(function=function.__name__), patch.object(repo, 'get_connection', return_value=db):
                with self.assertRaises(Error): function(value)
            cur.close.assert_called_once(); db.close.assert_called_once()
