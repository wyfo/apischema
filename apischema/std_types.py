import re
import sys
from base64 import b64decode, b64encode
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
from pathlib import Path
from typing import NewType, Type, TypeVar
from uuid import UUID

from apischema.json_schema.schema import schema
from apischema.conversions.converters import deserializer, serializer

Cls = TypeVar("Cls", bound=Type)


def as_str(cls: Cls, format: str = None):
    str_type = schema(format=format)(NewType(cls.__name__, str))
    deserializer(cls, str_type, cls)
    serializer(str, cls, str_type)


# =================== bytes =====================

deserializer(b64decode, str, bytes)


@serializer
def to_base64(b: bytes) -> str:
    return b64encode(b).decode()


# ================== datetime ===================

if sys.version_info >= (3, 7):  # pragma: no cover
    for cls, format in [(date, "date"), (datetime, "date-time"), (time, "time")]:
        str_type = schema(format=format)(NewType(cls.__name__, str))
        deserializer(cls.fromisoformat, str_type, cls)  # type: ignore
        serializer(cls.isoformat, cls, str_type)  # type: ignore

# ================== decimal ====================

deserializer(Decimal, float, Decimal)
serializer(float, Decimal, float)

# ================= ipaddress ===================

for cls in (IPv4Address, IPv4Interface, IPv4Network):
    as_str(cls, "ipv4")
for cls in (IPv6Address, IPv6Interface, IPv6Network):
    as_str(cls, "ipv6")

# ==================== path =====================

as_str(Path)

# =================== pattern ===================

Pattern = type(re.compile(r""))
deserializer(re.compile, str, Pattern)
serializer(lambda p: p.pattern, Pattern, str)

# ==================== uuid =====================

as_str(UUID, "uuid")
