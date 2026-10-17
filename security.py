"""Request-local authorization and signed-cookie session lifetime controls."""
import hashlib
import hmac
import math
import os
import time
from datetime import timedelta

from flask import current_app, flash, g, jsonify, redirect, request, session, url_for


SESSION_VERSION = 1


def _now():
    return time.time()


def configure_security(app, environ=None):
    env = os.environ if environ is None else environ
    mode = env.get('ERP_ENV', 'development').lower()
    if mode not in ('development', 'testing', 'production'):
        raise RuntimeError('ERP_ENV must be development, testing, or production.')
    key = env.get('SECRET_KEY', '')
    if not key or not key.strip():
        raise RuntimeError('SECRET_KEY is missing from the environment.')
    if mode == 'production' and (len(key.encode()) < 32 or 'YOUR_SECRET_KEY' in key.upper()):
        raise RuntimeError('Production requires a strong, randomly generated SECRET_KEY of at least 32 bytes.')
    debug_value = env.get('ERP_DEBUG', 'false').lower()
    if debug_value not in ('true', 'false', '1', '0'):
        raise RuntimeError('ERP_DEBUG must be true or false.')
    debug = debug_value in ('true', '1')
    if mode == 'production' and debug:
        raise RuntimeError('Debug mode is forbidden in production.')
    durations = {}
    for setting, default in (('SESSION_IDLE_SECONDS', 1800), ('SESSION_ABSOLUTE_SECONDS', 28800)):
        try:
            value = int(env.get('ERP_' + setting, default))
        except (TypeError, ValueError):
            raise RuntimeError('ERP_' + setting + ' must be a positive integer.') from None
        if value <= 0:
            raise RuntimeError('ERP_' + setting + ' must be a positive integer.')
        durations[setting] = value
    app.config.update(SECRET_KEY=key, ERP_ENV=mode, DEBUG=debug,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=(mode == 'production'),
                      PERMANENT_SESSION_LIFETIME=timedelta(seconds=durations['SESSION_ABSOLUTE_SECONDS']), **durations)


def credential_marker(user):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    payload = f"erp-session-v1\0{user['user_id']}\0{user['password_hash']}".encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def begin_session(user):
    session.clear()
    now = _now()
    session.update(user_id=user['user_id'], username=user['username'], role_id=user['role_id'],
                   role_name=user['role_name'], auth_version=SESSION_VERSION,
                   auth_started=now, auth_seen=now, credential_marker=credential_marker(user))
    session.permanent = False


def authenticated():
    return g.get('authorization') is not None


def has_permission(permission):
    state = g.get('authorization')
    return state is not None and permission in state['permissions']


def _reauthenticate():
    session.clear()
    if request.is_json or request.accept_mimetypes.best == 'application/json':
        return jsonify(error='authentication_required'), 401
    flash('Your session is no longer valid. Please log in again.', 'warning')
    return redirect(url_for('login'))


def init_security(app, loader):
    @app.before_request
    def refresh_authorization():
        g.authorization = None
        if (request.endpoint in (None, 'static') or 'user_id' not in session
                or (request.endpoint == 'logout' and request.method in ('GET', 'HEAD'))):
            return None
        now = _now()
        started, seen = session.get('auth_started'), session.get('auth_seen')
        timestamps = (started, seen)
        valid_times = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                          and math.isfinite(value) for value in timestamps)
        marker = session.get('credential_marker')
        if (session.get('auth_version') != SESSION_VERSION or not valid_times
                or not isinstance(marker, str) or len(marker) != 64
                or any(char not in '0123456789abcdef' for char in marker)
                or started > seen or seen > now + 60
                or now - seen >= app.config['SESSION_IDLE_SECONDS']
                or now - started >= app.config['SESSION_ABSOLUTE_SECONDS']):
            return _reauthenticate()
        try:
            user = loader(session['user_id'])
        except Exception:
            app.logger.exception('Unable to refresh request authorization.')
            if request.endpoint == 'logout':
                # Permit only local session removal with best-effort audit during
                # an outage; no cached permission can authorize a business action.
                g.authorization = {'permissions': frozenset()}
                return None
            if request.is_json or request.accept_mimetypes.best == 'application/json':
                return jsonify(error='authorization_unavailable'), 503
            return 'Authorization is temporarily unavailable. Please try again.', 503
        if (not user or user['user_id'] != session['user_id'] or not user['is_active'] or user['role_name'] is None
                or not hmac.compare_digest(marker, credential_marker(user))):
            return _reauthenticate()
        g.authorization = {key: value for key, value in user.items() if key != 'password_hash'}
        session.pop('permissions', None)
        for key in ('username', 'role_id', 'role_name'):
            if session.get(key) != user[key]:
                session[key] = user[key]
        session['auth_seen'] = now
        return None
