"""Company Postgres pushdown with pinned destinations and encrypted credentials."""
import json
import os
import socket
import ipaddress
import time
from pathlib import Path
from cryptography.fernet import Fernet

from backend.app.dataplane.config import Limits
from backend.app.dataplane.engine import scalar
from backend.app.dataplane.storage import fingerprint
from backend.app.dataplane.validator import validate


def cipher(limits: Limits, *, create=False):
    path = limits.credential_key_file
    if path.is_symlink():
        raise ValueError("Invalid credential key path")
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as key:
                key.write(Fernet.generate_key())
    return Fernet(path.read_bytes())


def encrypt(config: dict, limits: Limits):
    validate_destination(config, limits, resolve=False)
    return cipher(limits, create=True).encrypt(json.dumps(config).encode()).decode()


def decrypt(token: str, limits: Limits):
    return json.loads(cipher(limits).decrypt(token.encode()))


def validate_destination(config, limits, *, resolve=True):
    hosts = {h.strip().lower() for h in limits.postgres_hosts.split(",") if h.strip()}
    if config["host"].lower() not in hosts:
        raise ValueError("Company database host is not allowlisted")
    if config.get("sslmode", "verify-full") != "verify-full":
        raise ValueError("Verified TLS is required")
    if not resolve:
        return None
    addresses = socket.getaddrinfo(config["host"], config.get("port", 5432), type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Company database host could not be resolved")
    values = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if any(v.is_loopback or v.is_link_local or v.is_multicast or v.is_unspecified for v in values):
        raise ValueError("Forbidden database destination")
    return str(values[0])


class PostgresEngine:
    name = "postgres"

    def __init__(self, config, limits):
        import psycopg
        self.limits, self.config = limits, config
        address = validate_destination(config, limits)
        # No client-provided DSN, options, file paths, or search_path.
        self.connection = psycopg.connect(host=config["host"], hostaddr=address,
            port=config.get("port", 5432), dbname=config["database"], user=config["username"],
            password=config["password"], sslmode="verify-full", connect_timeout=5,
            sslrootcert=str(limits.postgres_ca_file) if limits.postgres_ca_file else "system",
            application_name="analyst_dataplane", options="-c default_transaction_read_only=on")
        self.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        self.connection.execute("SELECT set_config('statement_timeout', %s, true)", (str(limits.timeout_s*1000),))
        self.connection.execute("SELECT set_config('lock_timeout', '3000', true)")
        self.connection.execute("SELECT set_config('search_path', 'pg_catalog', true)")
        role = self.connection.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if any(role):
            self.close()
            raise ValueError("A non-privileged read-only company role is required")
        self._schema = dict(self.connection.execute(
            "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (config["schema_name"], config["table"])).fetchall())
        if not self._schema or len(self._schema) > limits.max_columns:
            self.close()
            raise ValueError("Company table unavailable or too wide")
        qualified = '"' + config["schema_name"].replace('"', '""') + '"."' + config["table"].replace('"', '""') + '"'
        if self.connection.execute("SELECT has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE')", (qualified,)).fetchone()[0]:
            self.close()
            raise ValueError("Company role must have SELECT-only table privileges")
        self.transaction_snapshot = self.connection.execute("SELECT pg_current_snapshot()::text").fetchone()[0]

    def schema(self):
        return self._schema

    def health(self):
        return {"engine": self.name, "ready": True}

    def _sql(self, sql):
        import sqlglot
        from sqlglot import exp
        from psycopg import sql as pgsql
        tree = validate(sql, self._schema, self.limits.result_rows)
        for table in tree.find_all(exp.Table):
            table.set("this", exp.Identifier(this=self.config["table"], quoted=True))
            table.set("db", exp.Identifier(this=self.config["schema_name"], quoted=True))
        generated = tree.sql(dialect="postgres")
        # sqlglot's positional placeholder is rendered as %s for psycopg.
        return generated.replace("?", "%s")

    def explain(self, sql, parameters):
        query = self._sql(sql)
        plan = self.connection.execute("EXPLAIN (FORMAT JSON) "+query, parameters).fetchone()[0]
        root = plan[0]["Plan"]
        def scan_rows(node):
            own = node.get("Plan Rows", 0) if "Scan" in node.get("Node Type", "") else 0
            return own + sum(scan_rows(c) for c in node.get("Plans", []))
        estimate = scan_rows(root)*max(1, root.get("Plan Width", 1))
        if estimate > self.limits.scan_mb*1024**2:
            raise ValueError("Estimated company query exceeds scan budget")
        return {"estimated_cost": root["Total Cost"], "estimated_scan_bytes": estimate,
                "estimate_only": True, "cost_unit": "Postgres planner units"}

    def execute(self, sql, parameters):
        query = self._sql(sql)
        estimate = self.explain(sql, parameters)
        started = time.perf_counter()
        cursor = self.connection.cursor(name="bounded_result")
        cursor.execute(query, parameters)
        rows, size = [], 0
        for row in cursor:
            record = dict(zip([c.name for c in cursor.description], map(scalar, row)))
            size += len(json.dumps(record, allow_nan=False).encode())
            if len(rows) >= self.limits.result_rows or size > self.limits.result_bytes:
                raise ValueError("Company result budget exceeded")
            rows.append(record)
        version = self.connection.info.server_version
        return {"rows": rows, "result_rows": len(rows), "result_bytes": size,
                "engine": "postgres", "engine_version": str(version),
                "elapsed_ms": round((time.perf_counter()-started)*1000, 3), **estimate,
                "query_hash": fingerprint({"sql": query, "parameters": parameters}),
                "result_hash": fingerprint(rows), "sql": query, "parameters": parameters,
                "transaction_snapshot": self.transaction_snapshot,
                "consistency": "read-only transaction; remote data is not an immutable local snapshot"}

    def close(self):
        self.connection.rollback()
        self.connection.close()
