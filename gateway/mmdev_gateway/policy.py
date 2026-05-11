from __future__ import annotations

import os
import tomllib
from pathlib import Path
from threading import Lock
from typing import Any


class GatewayPolicy:
    def __init__(self, path_env: str = "MMDEV_GATEWAY_POLICY_PATH") -> None:
        self.path_env = path_env
        self._lock = Lock()
        self._path: Path | None = None
        self._mtime_ns: int | None = None
        self._data: dict[str, Any] = {}

    def get_raw(self, env_name: str, default: Any) -> Any:
        self._reload_if_needed()
        key = self._to_policy_key(env_name)
        if key in self._data:
            return self._data[key]
        value = os.getenv(env_name)
        if value is None or value == "":
            return default
        return value

    def get_bool(self, env_name: str, default: bool = False) -> bool:
        value = self.get_raw(env_name, default)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "on"}

    def get_int(self, env_name: str, default: int = 0) -> int:
        value = self.get_raw(env_name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_float(self, env_name: str, default: float = 0.0) -> float:
        value = self.get_raw(env_name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_csv_set(self, env_name: str, *, upper: bool) -> set[str]:
        value = self.get_raw(env_name, "")
        if isinstance(value, list):
            items = {str(item).strip() for item in value if str(item).strip()}
        else:
            items = {item.strip() for item in str(value).split(",") if item.strip()}
        if upper:
            return {item.upper() for item in items}
        return {item.lower() for item in items}

    def _to_policy_key(self, env_name: str) -> str:
        prefix = "MMDEV_GATEWAY_"
        name = env_name[len(prefix) :] if env_name.startswith(prefix) else env_name
        return name.lower()

    def _reload_if_needed(self) -> None:
        path = self._resolve_policy_path()
        with self._lock:
            if path != self._path:
                self._path = path
                self._mtime_ns = None
                self._data = {}
            if path is None or not path.exists():
                self._mtime_ns = None
                self._data = {}
                return
            mtime_ns = path.stat().st_mtime_ns
            if self._mtime_ns == mtime_ns:
                return
            try:
                with path.open("rb") as fh:
                    payload = tomllib.load(fh)
            except Exception:
                payload = {}
            self._data = payload if isinstance(payload, dict) else {}
            self._mtime_ns = mtime_ns

    def _resolve_policy_path(self) -> Path | None:
        value = os.getenv(self.path_env)
        if not value:
            return None
        return Path(value).expanduser().resolve()
