#!/usr/bin/env python3
# items.py
import fcntl
import os
import tempfile
from typing import List, Iterable

"""
Somewhat crude API to use a regular list-like file as a database.
Safe writes, safe reads and idempotency.
"""


class ItemsDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def _lock(self, fd, exclusive: bool):
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    def _unlock(self, fd):
        fcntl.flock(fd, fcntl.LOCK_UN)

    def list(self) -> List[str]:
        with open(self.path, "a+", encoding="utf-8") as f:
            self._lock(f.fileno(), exclusive=False)
            f.seek(0)
            items = [line.rstrip("\n") for line in f if line.rstrip("\n") != ""]
            self._unlock(f.fileno())
        return items

    def contains(self, item: str) -> bool:
        with open(self.path, "a+", encoding="utf-8") as f:
            self._lock(f.fileno(), exclusive=False)
            f.seek(0)
            for line in f:
                if line.rstrip("\n") == item:
                    self._unlock(f.fileno())
                    return True
            self._unlock(f.fileno())
        return False

    def add(self, item: str) -> bool:
        # idempotent add; uses O_APPEND under exclusive lock
        with open(self.path, "a+", encoding="utf-8") as f:
            self._lock(f.fileno(), exclusive=True)
            f.seek(0)
            items = {line.rstrip("\n") for line in f if line.rstrip("\n") != ""}
            if item in items:
                self._unlock(f.fileno())
                return False
            f.write(item + "\n")
            f.flush()
            os.fsync(f.fileno())
            self._unlock(f.fileno())
        return True

    def remove(self, item: str) -> bool:
        dirpath = os.path.dirname(self.path) or "."
        with open(self.path, "a+", encoding="utf-8") as f:
            self._lock(f.fileno(), exclusive=True)
            f.seek(0)
            items = [line.rstrip("\n") for line in f if line.rstrip("\n") != ""]
            if item not in items:
                self._unlock(f.fileno())
                return False
            new_items = [x for x in items if x != item]
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp.", dir=dirpath)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tf:
                    for it in new_items:
                        tf.write(it + "\n")
                    tf.flush()
                    os.fsync(tf.fileno())
                os.replace(tmp_path, self.path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            self._unlock(f.fileno())
        return True

    def replace_all(self, items: Iterable[str]) -> None:
        dirpath = os.path.dirname(self.path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp.", dir=dirpath)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                for it in items:
                    tf.write(it.rstrip("\n") + "\n")
                tf.flush()
                os.fsync(tf.fileno())
            # acquire exclusive lock while swapping to avoid races
            with open(self.path, "a+", encoding="utf-8") as f:
                self._lock(f.fileno(), exclusive=True)
                os.replace(tmp_path, self.path)
                self._unlock(f.fileno())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
