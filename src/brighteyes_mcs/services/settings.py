"""The settings tree of the mcs service: one FastCS attribute per physical setting."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrRW, AttrW
from fastcs.controllers import BaseController, Controller, ControllerVector
from fastcs.datatypes import Bool, DataType, Enum, Float, Int, String, Waveform

from brighteyes_mcs.services.physical import SETTINGS, Setting, Source

#: Decimals a setting in physical units keeps, enough for a 25 ns cycle in seconds.
DECIMALS = 9

#: Groups whose children are numbered, such as `lasers.1`.
NUMBERED_GROUPS = ("lasers", "analog_out")


@dataclass
class SettingRef(AttributeIORef):
    """Names the setting an attribute serves."""

    path: str = ""


class SettingIO(AttributeIO[Any, SettingRef]):
    """Hands a put of a setting to the controller."""

    def __init__(self, put: Callable[[str, Any], Awaitable[None]]) -> None:
        super().__init__()
        self.put = put

    async def send(self, attr: AttrW[Any, SettingRef], value: Any) -> None:
        await self.put(attr.io_ref.path, value)


def datatype(setting: Setting) -> DataType[Any]:
    """Return the datatype a setting is served as."""
    match setting.kind:
        case "bool":
            return Bool()
        case "int":
            return Int(min=setting.minimum, max=setting.maximum)
        case "float":
            return Float(prec=DECIMALS)
        case "source":
            return Enum(Source)
        case "floats":
            return Waveform(np.float64, (setting.length,))
        case "ints":
            # PVAccess's NTNDArray has no 64-bit integer arrays.
            return Waveform(np.int32, (setting.length,))
        case "text":
            return String()


def build_tree(
    root: Controller, paths: Sequence[str], io: SettingIO
) -> dict[str, AttrR[Any, SettingRef]]:
    """Add the sub-controllers and attributes of `paths` under `root`; return them by path."""
    nodes: dict[tuple[str, ...], BaseController] = {(): root}
    attributes: dict[str, AttrR[Any, SettingRef]] = {}
    for path in paths:
        *groups, name = path.split(".")
        for depth in range(1, len(groups) + 1):
            key = tuple(groups[:depth])
            if key in nodes:
                continue
            parent = nodes[key[:-1]]
            child: BaseController
            if key == (groups[0],) and groups[0] in NUMBERED_GROUPS:
                child = ControllerVector({}, ios=[io])
            else:
                child = Controller(ios=[io])
            if isinstance(parent, ControllerVector):
                assert isinstance(child, Controller)
                parent[int(key[-1])] = child
            else:
                parent.add_sub_controller(key[-1], child)
            nodes[key] = child
        setting = SETTINGS[path]
        kind = AttrRW if setting.writable else AttrR
        attribute = kind(datatype(setting), io_ref=SettingRef(path=path))
        nodes[tuple(groups)].add_attribute(name, attribute)
        attributes[path] = attribute
    return attributes
