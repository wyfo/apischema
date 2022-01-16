from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import mashumaro
from common import Benchmark, Methods, Payment


@dataclass(frozen=True)
class Message(mashumaro.DataClassDictMixin):
    title: str
    body: str
    addresses: Optional[list[str]] = None  # no Python 3.10 support in 2.9.1...
    persistence: Optional[int] = None


@dataclass(frozen=True)
class Client(mashumaro.DataClassDictMixin):
    id: int
    first_name: str = field(metadata=mashumaro.field_options(alias="firstName"))
    last_name: str = field(metadata=mashumaro.field_options(alias="lastName"))

    def __post_init__(self):  # The only way I've found to add constraints
        if self.id < 0:
            raise ValueError


@dataclass(frozen=True)
class Item(mashumaro.DataClassDictMixin):
    name: str
    price: float
    quantity: int = 1

    def __post_init__(self):
        if self.price < 0 or self.quantity < 1:
            raise ValueError


@dataclass(frozen=True)
class Receipt(mashumaro.DataClassDictMixin):
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Optional[Client] = None
    special_offers: Optional[float] = field(
        default=None, metadata=mashumaro.field_options(alias="specialOffers")
    )

    def __post_init__(self):
        if self.special_offers is not None and self.special_offers < 0:
            raise ValueError


def methods(cls: type[mashumaro.DataClassDictMixin]) -> Methods:
    return Methods(cls.from_dict, cls.to_dict)


benchmarks = Benchmark(methods(Message), methods(Receipt))
