"""Global CSRF validation and explicit, payload-preserving expiry recovery."""
import hmac

from flask import jsonify, render_template, request, session
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from itsdangerous import BadData, URLSafeTimedSerializer

csrf = CSRFProtect()


def init_csrf(app):
    app.config.update(WTF_CSRF_METHODS={'POST', 'PUT', 'PATCH', 'DELETE'},
                      WTF_CSRF_ENABLED=True, WTF_CSRF_CHECK_DEFAULT=True,
                      WTF_CSRF_TIME_LIMIT=3600)
    csrf.init_app(app)

    @app.get('/auth/csrf-token')
    def csrf_token_refresh():
        response = jsonify(csrf_token=generate_csrf())
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.is_json or request.accept_mimetypes.best == 'application/json':
            return jsonify(error='csrf_failed', message=error.description), 400
        retry_fields = None
        # Only an authentically signed token for this session may recover. In
        # particular an expired token from another session must not qualify.
        if (error.description == 'The CSRF token has expired.' and request.method == 'POST'
                and request.form and not request.files
                and not any(any(word in name.lower() for word in ('password', 'secret'))
                            for name in request.form)):
            try:
                # validate_csrf(time_limit=None) uses the configured lifetime.
                # Verify the signature without an age limit ONLY to decide whether
                # to offer an explicit recovery form; it never executes an action.
                secret = app.config.get('WTF_CSRF_SECRET_KEY') or app.secret_key
                signed_seed = URLSafeTimedSerializer(secret, salt='wtf-csrf-token').loads(
                    request.form.get('csrf_token'), max_age=None)
                if not hmac.compare_digest(session.get('csrf_token', ''), signed_seed):
                    raise ValueError('Different session')
            except (BadData, ValueError, TypeError):
                pass
            else:
                retry_fields = [(name, value) for name, value in request.form.items(multi=True)
                                if name != 'csrf_token']
        return render_template('security/csrf_error.html', reason=error.description,
                               retry_fields=retry_fields, retry_path=request.full_path if request.query_string else request.path), 400

    @app.after_request
    def prevent_token_caching(response):
        if response.mimetype == 'text/html' or request.endpoint == 'csrf_token_refresh':
            response.headers['Cache-Control'] = 'no-store'
        return response
