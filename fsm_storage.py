# fsm_storage.py
"""SQLite-хранилище FSM: активный сценарий переживает перезапуск бота."""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from db import db_conn


class SQLiteStorage(BaseStorage):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @staticmethod
    def _key_values(key: StorageKey) -> tuple:
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id or 0,
            key.business_connection_id or "",
            key.destiny,
        )

    @staticmethod
    def _state_value(state: StateType) -> str | None:
        if isinstance(state, State):
            return state.state
        return state

    def _set_state_sync(self, key: StorageKey, state: StateType) -> None:
        values = self._key_values(key)
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO fsm_states
                    (bot_id, chat_id, user_id, thread_id,
                     business_connection_id, destiny, state, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
                ON CONFLICT (
                    bot_id, chat_id, user_id, thread_id,
                    business_connection_id, destiny
                ) DO UPDATE SET
                    state = excluded.state,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (*values, self._state_value(state)),
            )

    def _get_state_sync(self, key: StorageKey) -> str | None:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT state FROM fsm_states
                WHERE bot_id = ? AND chat_id = ? AND user_id = ?
                  AND thread_id = ? AND business_connection_id = ?
                  AND destiny = ?
                """,
                self._key_values(key),
            ).fetchone()
        return row["state"] if row else None

    def _set_data_sync(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        values = self._key_values(key)
        payload = json.dumps(data, ensure_ascii=False, default=str)
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO fsm_states
                    (bot_id, chat_id, user_id, thread_id,
                     business_connection_id, destiny, state, data)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT (
                    bot_id, chat_id, user_id, thread_id,
                    business_connection_id, destiny
                ) DO UPDATE SET
                    data = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (*values, payload),
            )

    def _get_data_sync(self, key: StorageKey) -> dict[str, Any]:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT data FROM fsm_states
                WHERE bot_id = ? AND chat_id = ? AND user_id = ?
                  AND thread_id = ? AND business_connection_id = ?
                  AND destiny = ?
                """,
                self._key_values(key),
            ).fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row["data"] or "{}")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_state_sync, key, state)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_state_sync, key)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_data_sync, key, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._get_data_sync, key)

    async def close(self) -> None:
        return None
