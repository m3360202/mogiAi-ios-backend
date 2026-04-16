"""Wrapper for SnowflakeGenerator with graceful fallback when dependency is missing."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Iterator


try:  # pragma: no cover - relies on external package
    from snowflake import SnowflakeGenerator as _SnowflakeGenerator  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed when dependency absent

    class _SnowflakeGenerator(Iterator[int]):
        """Lightweight fallback Snowflake-like generator.

        Generates roughly time-ordered 64-bit integers using milliseconds and a per-ms counter.
        """

        def __init__(self, *_args, **_kwargs) -> None:
            self._lock = threading.Lock()
            self._last_ms = 0
            self._sequence = 0

        def __next__(self) -> int:
            with self._lock:
                current_ms = int(time.time() * 1000)
                if current_ms == self._last_ms:
                    self._sequence = (self._sequence + 1) & 0xFFF  # 12-bit sequence
                    if self._sequence == 0:
                        while int(time.time() * 1000) <= self._last_ms:
                            time.sleep(0.001)
                        current_ms = int(time.time() * 1000)
                else:
                    self._sequence = 0
                    self._last_ms = current_ms

                snowflake_id = (current_ms << 12) | self._sequence
                return snowflake_id

        # Python's iterator protocol optionally allows __iter__ returning self
        def __iter__(self) -> "_SnowflakeGenerator":
            return self

else:  # pragma: no cover
    class _SnowflakeGenerator(_SnowflakeGenerator):  # type: ignore
        pass


SnowflakeGenerator = _SnowflakeGenerator


