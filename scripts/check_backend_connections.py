"""Read-only backend connectivity probes; never print credentials or tokens."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The invoking desktop shell may use DEBUG=release for unrelated software.
os.environ["DEBUG"] = "false"

from backend.app.core.config import Settings


def main():
    settings = Settings()

    def postgres():
        import psycopg

        with psycopg.connect(settings.postgres_dsn.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1, to_regclass('public.users') IS NOT NULL")
                value, users_table_exists = cursor.fetchone()
        return {"select_one": value == 1, "users_table_exists": users_table_exists}

    def redis_probe():
        import redis

        with redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5) as client:
            return {"ping": client.ping()}

    def jwks():
        url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.load(response)
        if not data.get("keys"):
            raise ValueError("JWKS contains no signing keys")
        return {"public_signing_keys": len(data["keys"])}

    def probe(name, operation):
        try:
            return {"check": name, "status": "PASS", "details": operation()}
        except Exception as exc:
            return {"check": name, "status": "FAIL", "error_type": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda item: probe(*item), [("postgresql", postgres), ("redis", redis_probe), ("supabase_jwks", jwks)]))
    print(json.dumps(results, indent=2))
    return int(any(result["status"] == "FAIL" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
