import operator
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
from typing import Deque, List, TypeVar
from uuid import UUID

from apischema import deserializer, schema, serializer, type_name
from apischema.conversions import Conversion, as_str

T = TypeVar("T")


# =================== bytes =====================

deserializer(Conversion(b64decode, source=str, target=bytes))


@serializer
def to_base64(b: bytes) -> str:
    return b64encode(b).decode()


type_name(graphql="Bytes")(bytes)
schema(encoding="base64")(bytes)


# ================ collections ==================

deserializer(Conversion(deque, source=List[T], target=Deque[T]))
serializer(Conversion(list, source=Deque[T], target=List[T]))
if sys.version_info < (3, 7):
    deserializer(Conversion(deque, source=List, target=deque))
    serializer(Conversion(list, source=deque, target=List))


# ================== datetime ===================

if sys.version_info >= (3, 7):  # pragma: no cover
    for cls, format in [(date, "date"), (datetime, "date-time"), (time, "time")]:
        deserializer(Conversion(cls.fromisoformat, source=str, target=cls))  # type: ignore
        serializer(Conversion(cls.isoformat, source=cls, target=str))  # type: ignore
        type_name(graphql=cls.__name__.capitalize())(cls)
        schema(format=format)(cls)

# ================== decimal ====================

deserializer(Conversion(Decimal, source=float, target=Decimal))
serializer(Conversion(float, source=Decimal, target=float))
type_name(None)(Decimal)

# ================= ipaddress ===================

for classes, format in [
    ((IPv4Address, IPv4Interface, IPv4Network), "ipv4"),
    ((IPv6Address, IPv6Interface, IPv6Network), "ipv6"),
]:
    for cls in classes:
        as_str(cls)
        type_name(graphql=cls.__name__)(cls)
        schema(format=format)(cls)

# ==================== path =====================

for cls in (PurePath, PurePosixPath, PureWindowsPath, Path, PosixPath, WindowsPath):
    as_str(cls)
    type_name(None)(cls)

# =================== pattern ===================

Pattern = type(re.compile(r""))
deserializer(Conversion(re.compile, source=str, target=Pattern))
serializer(Conversion(operator.attrgetter("pattern"), source=Pattern, target=str))
type_name(None)(Pattern)

# ==================== uuid =====================

as_str(UUID)
type_name(graphql="UUID")
schema(format="uuid")(UUID)
