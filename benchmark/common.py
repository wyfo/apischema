from collections.abc import Callable
from enum import Enum
from typing import NamedTuple

from apischema.utils import to_camel_case


class Methods(NamedTuple):
    deserializer: Callable
    serializer: Callable


class Benchmark(NamedTuple):
    simple: Methods
    complex: Methods
    library: str | None = None


class Payment(str, Enum):
    CASH = "CASH"
    CREDIT_CARD = "CREDIT_CARD"


to_camel_case = to_camel_case
