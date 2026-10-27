# heartbeat.py
"""Очень дешёвый heartbeat для watchdog: одна маленькая запись раз в минуту."""

import asyncio
import logging
from datetime import datetime

from config import HEARTBEAT_FILE, HEARTBEAT_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


def write_heartbeat() -> None:
    try:
        HEARTBEAT_FILE.write_text(
            datetime.now().isoformat(timespec="seconds"),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Не удалось записать heartbeat: %s", exc)


async def heartbeat_loop() -> None:
    while True:
        write_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
