"""Explicit security fixtures; never grant authority through cookie permissions."""
import time
from security import credential_marker, SESSION_VERSION


def user_state(user_id=7, permissions=(), username='acting.user', role_id=42, role_name='Test role', password_hash='test-only', is_active=True):
    return dict(user_id=user_id, username=username, role_id=role_id, role_name=role_name,
                password_hash=password_hash, is_active=is_active, permissions=frozenset(permissions))


def stamp_session(app, mapping, user):
    with app.app_context():
        marker=credential_marker(user)
    now=time.time()
    mapping.clear()
    mapping.update(user_id=user['user_id'], username=user['username'], role_id=user['role_id'],
                   role_name=user['role_name'], auth_version=SESSION_VERSION, auth_started=now,
                   auth_seen=now, credential_marker=marker)
