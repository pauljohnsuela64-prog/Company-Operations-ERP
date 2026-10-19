"""HTTP admission guard; installed before database-backed authorization."""
from flask import jsonify, make_response, request
import database


def maintenance_response():
    if request.is_json or request.accept_mimetypes.best == 'application/json':
        response = make_response(jsonify(error='service_unavailable'), 503)
    else:
        response = make_response('Service temporarily unavailable. Please try again later.', 503)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Retry-After'] = '5'
    return response


def init_schema_gate(app):
    # No import/startup network access. Every worker starts unready and performs
    # preflight before its first business request; readiness uses the same guard.
    @app.get('/health/live')
    def schema_liveness():
        return jsonify(status='alive')

    @app.get('/health/ready')
    def schema_readiness():
        response = jsonify(status='ready')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.before_request
    def admit_compatible_schema():
        if request.endpoint in ('static', 'schema_liveness'):
            return None
        try:
            database.ensure_ready()
        except database.SchemaUnavailable:
            # Logout remains local, CSRF protected, and reaches the existing
            # best-effort audit wrapper. Security's outage handling clears safely.
            if request.endpoint == 'logout':
                return None
            return maintenance_response()
        return None

    @app.errorhandler(database.SchemaUnavailable)
    def unavailable_during_request(error):
        return maintenance_response()
