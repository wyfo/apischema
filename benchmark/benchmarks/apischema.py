from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType

from common import Benchmark, Methods, Payment

import apischema

apischema.settings.camel_case = True
apischema.settings.deserialization.override_dataclass_constructors = True


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    addresses: list[str] | None = None
    persistence: int | None = None


PositiveFloat = NewType("PositiveFloat", float)
apischema.schema(min=0)(PositiveFloat)


@dataclass(frozen=True)
class Client:
    id: int = field(metadata=apischema.schema(min=0))
    first_name: str
    last_name: str


@dataclass(frozen=True)
class Item:
    name: str
    price: PositiveFloat
    quantity: int = field(default=1, metadata=apischema.schema(min=1))


@dataclass(frozen=True)
class Receipt:
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Client | None = None
    special_offers: PositiveFloat | None = None


def methods(cls: type) -> Methods:
    return Methods(
        apischema.deserialization_method(list[cls]),  # type: ignore
        apischema.serialization_method(list[cls]),  # type: ignore
    )


benchmarks = Benchmark(methods(Message), methods(Receipt))
