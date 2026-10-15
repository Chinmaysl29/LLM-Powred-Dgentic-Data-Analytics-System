"""Environment Management Engine for Phase 10.2.

Manages environment configuration separation across:
- Development
- Testing
- Staging
- Production

Provides:
- Environment variable validation & schema compliance
- Secret masking & redaction for logs
- Production security constraint validation (DEBUG=False, non-default secrets)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("deployment.environment")

ENV_ROOT = Path(__file__).resolve().parent.parent.parent


class EnvironmentManager:
    """Enterprise environment and configuration manager."""

    SUPPORTED_ENVIRONMENTS = {"development", "testing", "staging", "production"}

    MANDATORY_KEYS = [
        "APP_NAME",
        "ENVIRONMENT",
        "DEBUG",
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET_KEY",
    ]

    SECRET_KEYS = {
        "JWT_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "HUGGINGFACE_API_KEY",
    }

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else ENV_ROOT

    def get_env_file_path(self, env_name: str) -> Path:
        """Resolve file path for a named environment."""
        env_clean = env_name.lower().strip()
        if env_clean not in self.SUPPORTED_ENVIRONMENTS:
            raise ValueError(f"Unsupported environment: '{env_name}'. Must be one of {self.SUPPORTED_ENVIRONMENTS}")

        if env_clean == "development":
            p = self.root_dir / ".env"
            if p.exists():
                return p
        return self.root_dir / f".env.{env_clean}"

    def parse_env_file(self, env_name: str) -> dict[str, str]:
        """Parse KEY=VALUE lines from the corresponding env file."""
        file_path = self.get_env_file_path(env_name)
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        config: dict[str, str] = {}
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip("'\"")
                    config[key.strip()] = val
        return config

    def validate_environment(self, env_name: str) -> dict[str, Any]:
        """Validate environment constraints, missing keys, and security requirements."""
        config = self.parse_env_file(env_name)
        missing: list[str] = []
        violations: list[str] = []

        # Check mandatory keys
        for key in self.MANDATORY_KEYS:
            if key not in config or not config[key]:
                missing.append(key)

        # Production-specific constraints
        if env_name.lower() == "production":
            if config.get("DEBUG", "").lower() in {"true", "1", "yes"}:
                violations.append("DEBUG must be false in production")

            jwt_key = config.get("JWT_SECRET_KEY", "")
            if len(jwt_key) < 24:
                violations.append("JWT_SECRET_KEY in production must be at least 24 characters")
            if "mock" in jwt_key.lower() or "test" in jwt_key.lower():
                violations.append("Production cannot use a mock/test JWT_SECRET_KEY")

            db_pass = config.get("POSTGRES_PASSWORD", "")
            if db_pass.lower() in {"postgres", "password", "root", "admin"}:
                violations.append("Production POSTGRES_PASSWORD cannot be a default weak password")

        is_valid = (len(missing) == 0) and (len(violations) == 0)
        return {
            "environment": env_name.lower(),
            "is_valid": is_valid,
            "status": "PASS" if is_valid else "FAIL",
            "missing_keys": missing,
            "violations": violations,
            "total_keys_loaded": len(config),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_masked_config(self, env_name: str) -> dict[str, str]:
        """Return configuration with secret values securely masked."""
        config = self.parse_env_file(env_name)
        masked: dict[str, str] = {}

        for k, v in config.items():
            if any(secret_term in k for secret_term in self.SECRET_KEYS) or "KEY" in k or "SECRET" in k or "PASS" in k:
                if len(v) > 6:
                    masked[k] = f"{v[:2]}****{v[-2:]}"
                else:
                    masked[k] = "******"
            else:
                masked[k] = v

        return masked

    def apply_environment(self, env_name: str) -> dict[str, Any]:
        """Load and apply environment variables to os.environ safely."""
        val = self.validate_environment(env_name)
        if not val["is_valid"]:
            raise ValueError(f"Cannot apply invalid environment '{env_name}': {val['violations'] + val['missing_keys']}")

        config = self.parse_env_file(env_name)
        for k, v in config.items():
            os.environ[k] = v

        return {
            "environment": env_name.lower(),
            "applied_keys_count": len(config),
            "status": "APPLIED",
        }


# Global environment manager singleton
environment_manager = EnvironmentManager()
