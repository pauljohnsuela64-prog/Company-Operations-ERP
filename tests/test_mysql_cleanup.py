"""Shared disposable-launcher safety/failure paths; never use a database."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import mysql_audit_smoke as launcher


class MySQLCleanupTests(unittest.TestCase):
    def process(self):
        process = MagicMock(pid=123, returncode=0)
        process.poll.return_value = None
        return process

    def test_verification_checks_datadir_and_owned_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            pid = directory / 'disposable.pid'
            pid.write_text('123\n')
            connection = MagicMock()
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (folder, str(pid))
            launcher.verify_server(connection, directory, self.process())
            for values in ((str(directory / 'other'), str(pid)),
                           (folder, str(directory.parent / 'outside.pid'))):
                cursor.fetchone.return_value = values
                with self.assertRaises(launcher.IsolationError):
                    launcher.verify_server(connection, directory, self.process())
            cursor.fetchone.return_value = (folder, str(pid))
            pid.write_text('456')
            with self.assertRaises(launcher.IsolationError):
                launcher.verify_server(connection, directory, self.process())

    def test_unverified_process_never_receives_shutdown_or_termination(self):
        process = self.process()
        with patch.object(launcher.mysql.connector, 'connect') as connect:
            with self.assertRaises(launcher.IsolationError):
                launcher.stop_server(process, 1, Path('unused'), False)
        connect.assert_not_called()
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_shutdown_identity_mismatch_never_enters_fallback(self):
        process = self.process()
        with patch.object(launcher.mysql.connector, 'connect') as connect, \
                patch.object(launcher, 'verify_server', side_effect=launcher.IsolationError('mismatch')):
            with self.assertRaises(launcher.IsolationError):
                launcher.stop_server(process, 1, Path('unused'), True)
        connect.return_value.__enter__.return_value.cursor.assert_not_called()
        process.wait.assert_not_called()
        process.terminate.assert_not_called()

    def test_graceful_shutdown_verifies_before_shutdown_and_waits(self):
        process = self.process()
        process.poll.side_effect = [None, 0]
        order = []
        with patch.object(launcher.mysql.connector, 'connect') as connect, \
                patch.object(launcher, 'verify_server', side_effect=lambda *a: order.append('verify')):
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.execute.side_effect = lambda sql: order.append(sql)
            launcher.stop_server(process, 1, Path('unused'), True)
        self.assertEqual(order, ['verify', 'SHUTDOWN'])
        process.wait.assert_called_once_with(timeout=20)
        process.terminate.assert_not_called()

    def test_bounded_fallback_uses_only_owned_process_and_confirms_exit(self):
        process = self.process()
        process.poll.side_effect = [None, 1]
        process.wait.side_effect = [subprocess.TimeoutExpired('owned', 20),
                                    subprocess.TimeoutExpired('owned', 5), 1]
        with patch.object(launcher.mysql.connector, 'connect', side_effect=launcher.mysql.connector.Error('gone')):
            launcher.stop_server(process, 1, Path('unused'), True)
        self.assertEqual([c.kwargs['timeout'] for c in process.wait.call_args_list], [20, 5, 5])
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_failed_termination_is_infrastructure_failure(self):
        process = self.process()
        process.wait.side_effect = subprocess.TimeoutExpired('owned', 5)
        with patch.object(launcher.mysql.connector, 'connect', side_effect=launcher.mysql.connector.Error('gone')):
            with self.assertRaisesRegex(RuntimeError, 'termination failed'):
                launcher.stop_server(process, 1, Path('unused'), True)

    def test_failed_stop_retains_directory_and_does_not_mask_error(self):
        # A stopped mock process can safely exercise the outer cleanup guard;
        # no native server is spawned by this unit test.
        with tempfile.TemporaryDirectory() as outer:
            folder = Path(outer) / 'owned'
            folder.mkdir()
            process = self.process()
            process.poll.return_value = 0
            with patch.object(launcher.tempfile, 'mkdtemp', return_value=str(folder)), \
                    patch.object(launcher.subprocess, 'run', return_value=MagicMock(returncode=0)), \
                    patch.object(launcher.subprocess, 'Popen', return_value=process), \
                    patch.object(launcher, 'stop_server', side_effect=RuntimeError('termination failed')), \
                    patch.object(launcher, 'remove_stopped_directory') as remove:
                with self.assertRaisesRegex(RuntimeError, 'termination failed'):
                    with launcher.disposable_server('synthetic-binary'):
                        self.fail('Must not reach assertions before startup')
            remove.assert_not_called()
            self.assertTrue(folder.exists())


if __name__ == '__main__':
    unittest.main()
