"""Bounded OS-owned file locks; closing or process exit releases ownership."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time
import sys
from typing import Iterator

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_lock(path: Path, timeout: float = 15.0) -> Iterator[None]:
    """Lock a stable file, never delete it or infer ownership from its age."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while not acquired:
            try:
                if sys.platform == "win32":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("RECALL store is busy; retry the write.") from exc
                time.sleep(0.01)
        yield
    finally:
        try:
            if acquired:
                if sys.platform == "win32":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
