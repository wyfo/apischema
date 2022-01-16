from datetime import datetime

import attrs
import cattr
from common import Benchmark, Methods, Payment


@attrs.frozen
class Message:
    title: str
    body: str
    addresses: list[str] | None = None
    persistence: int | None = None


@attrs.frozen
class Client:
    id: int = attrs.field(validator=attrs.validators.ge(0))
    firstName: str  # Cattrs recommand using camelCase attributes
    lastName: str


@attrs.frozen
class Item:
    name: str
    price: float = attrs.field(validator=attrs.validators.ge(0))
    quantity: int = attrs.field(default=1, validator=attrs.validators.ge(1))


@attrs.frozen
class Receipt:
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Client | None = None
    specialOffers: float | None = attrs.field(
        default=None, validator=attrs.validators.optional(attrs.validators.ge(0))
    )


cattr.register_unstructure_hook(datetime, lambda v: v.isoformat())
cattr.register_structure_hook(datetime, lambda v, _: datetime.fromisoformat(v))


def methods(cls: type) -> Methods:
    return Methods(
        lambda data: cattr.structure(data, cls),  # type: ignore
        lambda obj: cattr.unstructure(obj, cls),  # type: ignore
    )


benchmark = Benchmark(methods(Message), methods(Receipt), "cattrs")
