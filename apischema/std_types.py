import re
import sys
from base64 import b64decode, b64encode
from collections import deque
from datetime import date, datetime, time
from decimal import Decimal
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Interface,
    IPv6Network,
)
from pathlib import (
    Path,
    PosixPath,
    PurePath,
    PurePosixPath,
    PureWindowsPath,
    WindowsPath,
)
from typing import Deque, List, NewType, TypeVar
from uuid import UUID

from apischema.conversions.converters import as_str, deserializer, serializer
from apischema.json_schema.schema import schema

T = TypeVar("T")


# =================== bytes =====================

deserializer(b64decode, str, bytes)


@serializer
def to_base64(b: bytes) -> str:
    return b64encode(b).decode()


# ================ collections ==================

deserializer(deque, List[T], Deque[T])
serializer(list, Deque[T], List[T])
if sys.version_info < (3, 7):
    deserializer(deque, List, deque)
    serializer(list, deque, List)


# ================== datetime ===================

if sys.version_info >= (3, 7):  # pragma: no cover
    for cls, format in [(date, "date"), (datetime, "date-time"), (time, "time")]:
        str_type = schema(format=format)(NewType(cls.__name__.capitalize(), str))
        deserializer(cls.fromisoformat, str_type, cls)  # type: ignore
        serializer(cls.isoformat, cls, str_type)  # type: ignore

# ================== decimal ====================

deserializer(Decimal, float, Decimal)
serializer(float, Decimal, float)

# ================= ipaddress ===================

for cls in (IPv4Address, IPv4Interface, IPv4Network):
    as_str(cls, format="ipv4")
for cls in (IPv6Address, IPv6Interface, IPv6Network):
    as_str(cls, format="ipv6")

# ==================== path =====================

for cls in (PurePath, PurePosixPath, PureWindowsPath, Path, PosixPath, WindowsPath):
    as_str(cls)

# =================== pattern ===================

Pattern = type(re.compile(r""))
deserializer(re.compile, str, Pattern)
serializer(lambda p: p.pattern, Pattern, str)

# ==================== uuid =====================

as_str(UUID, format="uuid")
