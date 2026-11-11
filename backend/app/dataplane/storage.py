"""Manifest-based paths; no basename searches and no mutable raw objects."""
import hashlib
import json
from pathlib import Path
from uuid import UUID


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str, allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def confined(root: Path, relative: str, *, exists=True) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Invalid artifact path")
    base = root.resolve()
    candidate = root / relative
    # Reject links even when they happen to resolve inside the allowed tree.
    if any(p.is_symlink() for p in [candidate, *candidate.parents] if p != base.parent):
        raise ValueError("Symlink artifacts are not supported")
    result = candidate.resolve()
    if not result.is_relative_to(base) or (exists and not result.is_file()):
        raise ValueError("Artifact is unavailable")
    return result


def scope_root(root: Path, tenant, workspace, actor) -> Path:
    return root / str(UUID(str(tenant))) / str(UUID(str(workspace))) / str(UUID(str(actor)))


def write_new_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(value))
