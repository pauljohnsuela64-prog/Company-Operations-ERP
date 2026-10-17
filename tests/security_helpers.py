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


from flask.testing import FlaskClient
from flask_wtf.csrf import generate_csrf
from werkzeug.datastructures import Headers


def csrf_token_for(client):
    """Issue a real Flask-WTF token for this client's actual signed session."""
    with client.session_transaction() as mapping:
        with client.application.test_request_context():
            from flask import session
            session.update(mapping)
            token = generate_csrf()
            mapping['csrf_token'] = session['csrf_token']
    return token


class CSRFClient(FlaskClient):
    """Existing workflow tests submit genuine tokens; rejection tests use raw clients."""
    def open(self, *args, **kwargs):
        if kwargs.get('method', 'GET').upper() in ('POST', 'PUT', 'PATCH', 'DELETE'):
            headers = Headers(kwargs.get('headers'))
            if 'X-CSRFToken' not in headers and 'X-CSRF-Token' not in headers:
                headers['X-CSRFToken'] = csrf_token_for(self)
            kwargs['headers'] = headers
        return super().open(*args, **kwargs)


def csrf_client(app):
    return CSRFClient(app, response_wrapper=app.response_class)
