"""Run the backend on Windows against this Compose stack's published services.

Overrides affect only this process; .env, Docker configuration and credentials
are unchanged. Run from the repository root: python scripts/run_local_backend.py
"""
from pathlib import Path
import os
import sys

from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    configured = {**dotenv_values(root / '.env'), **os.environ}
    for name, service, port in (
        ('DATABASE_URL', 'postgres', int(configured.get('POSTGRES_HOST_PORT', '5432'))),
        ('REDIS_URL', 'redis', 6379),
    ):
        if configured.get(name):
            url = make_url(configured[name])
            if url.host == service:
                os.environ[name] = url.set(host='127.0.0.1', port=port).render_as_string(hide_password=False)
    if configured.get('CHROMA_HOST') == 'chromadb':
        os.environ['CHROMA_HOST'] = '127.0.0.1'
        os.environ['CHROMA_PORT'] = '8401'
    if 'DEBUG' in configured and str(configured['DEBUG']).lower() not in {'true', 'false', '1', '0', 'yes', 'no', 'on', 'off'}:
        raise SystemExit('Invalid DEBUG: use true/false (or 1/0, yes/no, on/off).')
    import uvicorn
    uvicorn.run('backend.main:app', host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
