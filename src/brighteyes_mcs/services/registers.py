"""The registers of a bitfile, as the typed attributes the mcs service serves."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final

import numpy as np
from fastcs.datatypes import Bool, DataType, Float, Int, Waveform
from fastcs.datatypes._numeric import _Numeric
from nifpga.nifpga import DataType as NiType

from brighteyes_mcs.logging_setup import logger

NO_DESCRIPTION: Final = "No description available"

#: Largest whole number a double holds exactly.
EXACT_LIMIT: Final = 2**53

#: Names a FastCS attribute accepts.
VALID_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Range of each integer type the board has.
INTEGER_RANGES: Final[Mapping[NiType, tuple[int, int]]] = {
    NiType.I8: (-(2**7), 2**7 - 1),
    NiType.U8: (0, 2**8 - 1),
    NiType.I16: (-(2**15), 2**15 - 1),
    NiType.U16: (0, 2**16 - 1),
    NiType.I32: (-(2**31), 2**31 - 1),
    NiType.U32: (0, 2**32 - 1),
    NiType.I64: (-(2**63), 2**63 - 1),
    NiType.U64: (0, 2**64 - 1),
}

#: Element type of an array register, by the board's element type.
ARRAY_DTYPES: Final[Mapping[NiType, type[np.generic]]] = {
    NiType.Bool: np.bool_,
    NiType.I8: np.int8,
    NiType.U8: np.uint8,
    NiType.I16: np.int16,
    NiType.U16: np.uint16,
    NiType.I32: np.int32,
    NiType.U32: np.uint32,
    NiType.I64: np.int64,
    NiType.U64: np.uint64,
    NiType.Sgl: np.float32,
    NiType.Dbl: np.float64,
    NiType.Fxp: np.float64,
}


@dataclass(frozen=True)
class WholeFloat(Float):
    """A whole number served as a double, refusing fractions.

    `Float.validate` would round a fraction to `prec` before any check saw it.
    """

    prec: int = 0

    def validate(self, value: Any) -> float:
        whole = _Numeric.validate(self, value)
        # The range check runs on the converted value, which rounds an integer
        # past 2**53 onto the limit itself.
        if whole != value:
            raise ValueError(f"Value {value} is not exactly representable as a double")
        if not float(whole).is_integer():
            raise ValueError(f"Value {value} is not a whole number")
        return float(whole)


@dataclass(frozen=True)
class FxpFloat(Float):
    """A fixed-point value, rounded to the nearest step the board can hold."""

    step: float = 1.0
    prec: int = 6

    def validate(self, value: Any) -> float:
        checked = _Numeric.validate(self, value)
        return round(checked / self.step) * self.step


@dataclass(frozen=True)
class ExactWaveform(Waveform):
    """An array register: exactly `shape`, each element checked as its scalar type."""

    min: float | None = None
    max: float | None = None
    step: float | None = None
    whole: bool = False

    def validate(self, value: Any) -> np.ndarray:
        array = np.asarray(value)
        if array.shape != self.shape:
            raise ValueError(f"Value shape {array.shape} is not {self.shape}")
        if np.dtype(self.array_dtype) != np.bool_:
            array = array.astype(np.float64)
            if self.min is not None and np.any(array < self.min):
                raise ValueError(f"Value {array} has elements below {self.min}")
            if self.max is not None and np.any(array > self.max):
                raise ValueError(f"Value {array} has elements above {self.max}")
            if self.whole and not np.all(np.mod(array, 1) == 0):
                raise ValueError(f"Value {array} has elements that are not whole")
            if self.step is not None:
                array = np.round(array / self.step) * self.step
        return super().validate(array)


@dataclass(frozen=True)
class RegisterSpec:
    """One register of the bitfile, as the service serves it.

    `kind` is the board's type name, such as `"U32"`, and `length` is 1 for a
    scalar register.
    """

    name: str
    kind: str
    length: int
    writable: bool
    description: str
    datatype: DataType[Any]


def fxp_range(fxp_type: Any) -> tuple[float, float, float]:
    """Return the minimum, maximum and step of a fixed-point type.

    nifpga computes them from the word lengths and the sign, but keeps them in
    private attributes and offers no public way to read them.
    """
    return float(fxp_type._minimum), float(fxp_type._maximum), float(fxp_type._delta)


def array_element_type(array_type: Any) -> Any:
    """Return the element type of an array type, which nifpga keeps private."""
    return array_type._subtype


def scalar_datatype(kind: NiType, element_type: Any) -> DataType[Any] | None:
    """Return the datatype a scalar register of this type is served as, if any."""
    match kind:
        case NiType.Bool:
            return Bool()
        case NiType.I8 | NiType.U8 | NiType.I16 | NiType.U16 | NiType.I32:
            low, high = INTEGER_RANGES[kind]
            return Int(min=low, max=high)
        case NiType.U32 | NiType.I64 | NiType.U64:
            # FastCS serves every Int as a signed 32-bit NTScalar, although
            # PVAccess has 64-bit and unsigned integers, so these registers go
            # out as doubles, exact up to 2**53.
            # TODO: ask FastCS for a patch adding 64-bit and unsigned integers,
            # then serve these registers as integers again.
            low, high = INTEGER_RANGES[kind]
            return WholeFloat(min=max(low, -EXACT_LIMIT), max=min(high, EXACT_LIMIT))
        case NiType.Sgl | NiType.Dbl:
            return Float()
        case NiType.Fxp:
            minimum, maximum, step = fxp_range(element_type)
            return FxpFloat(min=minimum, max=maximum, step=step)
        case _:
            return None


def array_datatype(kind: NiType, element_type: Any, length: int) -> DataType[Any] | None:
    """Return the datatype an array register of this element type is served as, if any."""
    if kind not in ARRAY_DTYPES:
        return None
    low: float | None = None
    high: float | None = None
    step: float | None = None
    if kind in INTEGER_RANGES:
        low, high = INTEGER_RANGES[kind]
    elif kind is NiType.Fxp:
        low, high, step = fxp_range(element_type)
    return ExactWaveform(
        array_dtype=ARRAY_DTYPES[kind],
        shape=(length,),
        min=low,
        max=high,
        step=step,
        whole=kind in INTEGER_RANGES,
    )


def read_descriptions(text: str) -> dict[str, str]:
    """Return the description of each register row of a Markdown register table.

    A register row has four cells, a name that is not bold and a type. The
    header, the separator and the bold section rows are skipped. A section
    noted "(for all channels from 0 to 7)" describes its registers once, under
    channel 7, so each of its rows describes the same register of channels 0
    to 7.
    """
    descriptions = {}
    all_channels = False
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        name, kind, _, description = cells
        if name.startswith("**"):
            all_channels = False
        elif name.startswith("(for all channels"):
            all_channels = True
        if not kind or name.startswith("**") or name == "Name" or set(name) <= {"-"}:
            continue
        descriptions[name] = description
        if all_channels:
            for channel in range(7):
                descriptions[name.replace("_7_", f"_{channel}_")] = description
    return descriptions


def load_descriptions() -> dict[str, str]:
    """Return the descriptions of the register table packaged with the service."""
    table = resources.files(__package__).joinpath("registers.md")
    return read_descriptions(table.read_text(encoding="utf-8"))


def register_specs(bitfile: Any, descriptions: Mapping[str, str]) -> list[RegisterSpec]:
    """Return the specs of the registers of `bitfile` that the service can serve.

    Internal registers are left out, as `nifpga.Session` leaves them out.
    Registers of a type the service cannot serve, or whose name is not a valid
    attribute name, are left out with a warning.

    Parameters
    ----------
    bitfile
        An `nifpga.Bitfile`.
    descriptions
        Description of each register, by name.
    """
    specs = []
    for name, register in bitfile.registers.items():
        if register.is_internal():
            continue
        if VALID_NAME.fullmatch(name) is None:
            logger.warning("Register %r is not served: not a valid attribute name", name)
            continue
        kind = register.datatype
        if register.is_array():
            element_type = array_element_type(register.type)
            datatype = array_datatype(kind, element_type, len(register))
        else:
            datatype = scalar_datatype(kind, register.type)
        if datatype is None:
            logger.warning("Register %r is not served: type %s is not supported", name, kind)
            continue
        specs.append(
            RegisterSpec(
                name=name,
                kind=str(kind),
                length=len(register),
                writable=not register.is_indicator,
                # TODO: find out why the register table has no row for a
                # register that gets this placeholder.
                description=descriptions.get(name, NO_DESCRIPTION),
                datatype=datatype,
            )
        )
    return specs
