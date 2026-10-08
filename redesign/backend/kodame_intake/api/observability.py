"""Request correlation without cookies, query strings, document text or credentials."""
import logging
import time
import uuid

log = logging.getLogger('uvicorn.error')


async def request_telemetry(request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['X-Request-ID'] = request_id
        return response
    finally:
        route = request.scope.get('route')
        log.info('http request_id=%s method=%s route=%s status=%s duration_ms=%.1f',
                 request_id, request.method, getattr(route, 'path', 'unmatched'),
                 status, (time.monotonic()-started)*1000)
