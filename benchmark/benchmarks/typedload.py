from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import typedload.datadumper  # noqa
import typedload.dataloader  # noqa
from common import Benchmark, Methods, Payment


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    addresses: Optional[list[str]] = None  # no Python 3.10 support in 2.14
    persistence: Optional[int] = None


@dataclass(frozen=True)
class Client:
    id: int
    first_name: str = field(metadata={"name": "firstName"})
    last_name: str = field(metadata={"name": "lastName"})

    def __post_init__(self):  # The only way I've found to add constraints
        if self.id < 0:
            raise ValueError


@dataclass(frozen=True)
class Item:
    name: str
    price: float
    quantity: int = 1

    def __post_init__(self):
        if self.price < 0 or self.quantity < 1:
            raise ValueError


@dataclass(frozen=True)
class Receipt:
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Optional[Client] = None
    special_offers: Optional[float] = field(
        default=None, metadata={"name": "specialOffers"}
    )

    def __post_init__(self):
        if self.special_offers is not None and self.special_offers < 0:
            raise ValueError


loader = typedload.dataloader.Loader()
loader.handlers.insert(
    loader.index(datetime),
    (lambda tp: tp is datetime, lambda _, value, tp: datetime.fromisoformat(value)),
)
dumper = typedload.datadumper.Dumper()
dumper.handlers.insert(
    dumper.index(datetime.now()),
    (lambda tp: tp is datetime, lambda _, value, tp: value.isoformat()),
)


def methods(cls: type) -> Methods:
    load = loader.load
    return Methods(lambda data: load(data, cls), dumper.dump)  # type: ignore


benchmarks = Benchmark(methods(Message), methods(Receipt))
