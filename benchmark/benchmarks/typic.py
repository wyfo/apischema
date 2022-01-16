from dataclasses import dataclass
from datetime import datetime

import typic
from common import Benchmark, Methods, Payment


@typic.constrained(ge=0)
class PositiveFloat(float):
    ...


@typic.constrained(ge=0)
class PositiveInt(int):
    ...


@typic.constrained(ge=1)
class Quantity(int):
    ...


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    addresses: list[str] | None = None
    persistence: int | None = None


@dataclass(frozen=True)
class Client:
    id: PositiveInt
    firstName: str  # No camelcase handling ...
    lastName: str


@dataclass(frozen=True)
class Item:
    name: str
    price: PositiveFloat
    quantity: Quantity = Quantity(1)


@dataclass(frozen=True)
class Receipt:
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Client | None = None
    specialOffers: PositiveFloat | None = None


def methods(cls: type) -> Methods:
    proto = typic.protocol(cls)
    return Methods(proto.deserialize, proto.serialize)


benchmarks = Benchmark(methods(Message), methods(Receipt), "typical")
