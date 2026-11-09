"""Resource policy shared by API, supervisor and engine children."""
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Limits(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATAPLANE_", extra="ignore")
    enabled: bool = False
    engine_default: Literal["duckdb", "postgres"] = "duckdb"
    root: Path = Path("/app/storage/dataplane")
    memory_mb: int = Field(512, ge=64, le=8192)
    worker_memory_mb: int = Field(1024, ge=128, le=16384)
    threads: int = Field(2, ge=1, le=4)
    timeout_s: int = Field(120, ge=1, le=900)
    spill_mb: int = Field(2048, ge=64, le=16384)
    upload_mb: int = Field(100, ge=1, le=1024)
    scan_mb: int = Field(4096, ge=1, le=65536)
    result_rows: int = Field(5000, ge=1, le=5000)
    result_bytes: int = Field(1048576, ge=1024, le=8388608)
    batch_rows: int = Field(10000, ge=100, le=50000)
    max_columns: int = Field(200, ge=1, le=500)
    postgres_hosts: str = ""
    monitoring_interval_s: int = Field(3600, ge=60, le=86400)
    postgres_ca_file: Path | None = None
    credential_key_file: Path = Path("/app/storage/dataplane/credential.key")

    @model_validator(mode="after")
    def memory_budget(self):
        if self.memory_mb * 2 > self.worker_memory_mb:
            raise ValueError("Engine memory must not exceed half the worker budget")
        return self
