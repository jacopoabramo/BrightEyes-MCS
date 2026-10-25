"""File-level configuration operations with a stable legacy schema."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ...storage.legacy_config import LegacyConfigurationCodec


class ConfigurationController:
    def load(self, filename: str | Path) -> dict[str, Any]:
        return LegacyConfigurationCodec.load(filename)

    def save(self, filename, payload, *, encoder=None):
        LegacyConfigurationCodec.dump(filename, payload, encoder=encoder)
        return filename

    @staticmethod
    def merge_for_save(loaded_payload, current_payload):
        """Update known GUI values while retaining unknown legacy/future keys."""

        merged = deepcopy(dict(loaded_payload or {}))
        current = deepcopy(dict(current_payload or {}))
        old_plugins = merged.get("plugins")
        new_plugins = current.get("plugins")
        merged.update(current)
        if isinstance(old_plugins, dict) and isinstance(new_plugins, dict):
            plugins = deepcopy(old_plugins)
            plugins.update(new_plugins)
            merged["plugins"] = plugins
        return merged
