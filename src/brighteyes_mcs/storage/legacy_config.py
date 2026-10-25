"""Read and write the stable BrightEyes ``.cfg`` schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class NumpyJSONEncoder(json.JSONEncoder):
    """Encode NumPy arrays without changing the legacy JSON ``.cfg`` layout."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class LegacyConfigurationCodec:
    """Lossless dictionary boundary for legacy JSON-based ``.cfg`` files."""

    @staticmethod
    def loads(text: str) -> dict[str, Any]:
        payload = json.loads(text.replace(", \n", ","))
        if not isinstance(payload, dict):
            raise ValueError("BrightEyes configuration root must be a JSON object")
        return payload

    @classmethod
    def load(cls, filename: str | Path) -> dict[str, Any]:
        return cls.loads(Path(filename).read_text(encoding="utf-8"))

    @staticmethod
    def dumps(payload: Mapping[str, Any], *, encoder=None) -> str:
        kwargs = {"cls": encoder} if encoder is not None else {}
        return json.dumps(dict(payload), **kwargs).replace(",", ",\n")

    @classmethod
    def dump(cls, filename: str | Path, payload: Mapping[str, Any], *, encoder=None) -> None:
        Path(filename).write_text(cls.dumps(payload, encoder=encoder), encoding="utf-8")
