"""Durable raw storage shared by import and live collection."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_directory(path: Path) -> None:
    """Make new directory entries durable before creating response files."""
    if path.is_dir():
        return
    ensure_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    _sync_directory(path.parent)


def _save(path: Path, content: bytes, *, immutable: bool = False) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
            if immutable:
                # A hard link fails if a response already exists at the final path.
                os.link(temporary, path)
            else:
                temporary.replace(path)
            _sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)


def _save_record(path: Path, record: dict) -> None:
    _save(path, (json.dumps(record, indent=2) + "\n").encode())


@contextmanager
def collection_lock(data: Path):
    root = data / "pilot"
    ensure_directory(root)
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
