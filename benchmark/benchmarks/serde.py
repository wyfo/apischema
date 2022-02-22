from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import serde
from common import Benchmark, Methods, Payment
from serde.core import SETTINGS

SETTINGS["debug"] = True


@serde.serde
@dataclass(frozen=True)
class Message:
    title: str
    body: str
    addresses: Optional[list[str]] = None
    persistence: Optional[int] = None


@serde.serde
@dataclass(frozen=True)
class Client:
    id: int
    firstName: str
    lastName: str

    def __post_init__(self):  # The only way I've found to add constraints
        if self.id < 0:
            raise ValueError


@serde.serde
@dataclass(frozen=True)
class Item:
    name: str
    price: float
    quantity: int = 1

    def __post_init__(self):
        if self.price < 0 or self.quantity < 1:
            raise ValueError


@serde.serde
@dataclass(frozen=True)
class Receipt:
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Optional[Client] = None
    specialOffers: Optional[float] = None

    def __post_init__(self):
        if self.specialOffers is not None and self.specialOffers < 0:
            raise ValueError


def methods(cls: type) -> Methods:
    return Methods(lambda data: serde.from_dict(cls, data), serde.to_dict)


benchmarks = Benchmark(methods(Message), methods(Receipt), "pyserde")
