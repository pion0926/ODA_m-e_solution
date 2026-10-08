from unittest.mock import patch
import h11
from fastapi import Request
from kodame_intake.api import auth_routes as main


def test_logout_revokes_session_and_emits_valid_bodyless_204():
    name=main.SESSION_COOKIE_NAME
    request=Request({'type':'http','headers':[(b'cookie',f'{name}=test-session'.encode())]})
    with patch.object(main,'revoke_session') as revoke:
        response=main.auth_logout(request)
    revoke.assert_called_once_with('test-session')
    assert response.status_code==204
    assert 'Max-Age=0' in response.headers['set-cookie']
    # ASGI test clients accept a JSON null body here; the actual HTTP server
    # rejects it with "Too much data for declared Content-Length".
    wire=h11.Connection(h11.SERVER)
    wire.send(h11.Response(status_code=response.status_code,headers=response.raw_headers))
    assert wire.send(h11.Data(data=response.body))==b''
    wire.send(h11.EndOfMessage())
