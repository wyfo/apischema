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

from apischema.conversions import Conversion, as_str, deserializer, serializer
from apischema.json_schema.schema import schema

T = TypeVar("T")


# =================== bytes =====================

deserializer(Conversion(b64decode, source=str, target=bytes))


@serializer
def to_base64(b: bytes) -> str:
    return b64encode(b).decode()


# ================ collections ==================

deserializer(Conversion(deque, source=List[T], target=Deque[T]))
serializer(Conversion(list, source=Deque[T], target=List[T]))
if sys.version_info < (3, 7):
    deserializer(Conversion(deque, source=List, target=deque))
    serializer(Conversion(list, source=deque, target=List))


# ================== datetime ===================

if sys.version_info >= (3, 7):  # pragma: no cover
    for cls, format in [(date, "date"), (datetime, "date-time"), (time, "time")]:
        str_type = schema(format=format)(NewType(cls.__name__.capitalize(), str))
        deserializer(Conversion(cls.fromisoformat, source=str_type, target=cls))  # type: ignore # noqa: E501
        serializer(Conversion(cls.isoformat, source=cls, target=str_type))  # type: ignore # noqa: E501

# ================== decimal ====================

deserializer(Conversion(Decimal, source=float, target=Decimal))
serializer(Conversion(float, source=Decimal, target=float))

# ================= ipaddress ===================

for cls in (IPv4Address, IPv4Interface, IPv4Network):
    schema(format="ipv4")(as_str(cls))
for cls in (IPv6Address, IPv6Interface, IPv6Network):
    schema(format="ipv6")(as_str(cls))

# ==================== path =====================

for cls in (PurePath, PurePosixPath, PureWindowsPath, Path, PosixPath, WindowsPath):
    as_str(cls)

# =================== pattern ===================

Pattern = type(re.compile(r""))
deserializer(Conversion(re.compile, source=str, target=Pattern))
serializer(Conversion(lambda p: p.pattern, source=Pattern, target=str))


# ==================== uuid =====================

schema(format="uuid")(as_str(UUID))
