"""Temporary download directory cleanup."""
from __future__ import annotations

import logging
import shutil
import threading
import time

from .config import TEMP_DIR, TEMP_FILE_TTL_SEC

logger = logging.getLogger(__name__)


def cleanup_old_temp(ttl_sec=TEMP_FILE_TTL_SEC):
    now = time.time()
    removed = 0
    if not TEMP_DIR.exists():
        return 0
    for child in TEMP_DIR.iterdir():
        try:
            if not child.is_dir():
                continue
            age = now - child.stat().st_mtime
            if age > ttl_sec:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError as exc:
            logger.warning("cleanup failed for %s: %s", child, exc)
    return removed


def remove_dir(path):
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError as exc:
        logger.warning("remove_dir failed for %s: %s", path, exc)


def start_cleanup_loop(interval_sec=300):
    def _loop():
        while True:
            try:
                n = cleanup_old_temp()
                if n:
                    logger.info("cleaned %s temp dirs", n)
            except Exception as exc:
                logger.exception("cleanup loop error: %s", exc)
            time.sleep(interval_sec)

    t = threading.Thread(target=_loop, name="temp-cleanup", daemon=True)
    t.start()
    return t
