"""Fail closed before collection writes when the Chroma protocol is untested."""
from backend.app.core.exceptions import ChromaConnectionError

# Expand only after persistent collection round-trip/restart verification.
TESTED_CHROMA_PAIRS = frozenset({('0.6.3', '0.6.3')})


class ChromaCompatibilityError(ChromaConnectionError):
    error_code = 'CHROMA_VERSION_INCOMPATIBLE'


def verify_chroma_compatibility(client, client_version: str) -> dict:
    try:
        server_version = str(client.get_version())
    except Exception as exc:
        raise ChromaConnectionError('Chroma version probe unavailable') from exc
    if (client_version, server_version) not in TESTED_CHROMA_PAIRS:
        raise ChromaCompatibilityError(
            f'Chroma client {client_version} / server {server_version} is not a verified pairing')
    client.heartbeat()
    return {'client_version': client_version, 'server_version': server_version, 'compatible': True}
