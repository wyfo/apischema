from datetime import datetime
from typing import Generic, Optional, Type, TypeVar

import pydantic.generics
from common import Benchmark, Methods, Payment, to_camel_case


class CamelModel(pydantic.BaseModel):
    class Config:
        alias_generator = to_camel_case


class Message(CamelModel):
    title: str
    body: str
    addresses: Optional[list[str]] = None
    persistence: Optional[int] = None


class Client(CamelModel):
    id: int = pydantic.Field(ge=0)
    first_name: str
    last_name: str


class Item(CamelModel):
    name: str
    price: float = pydantic.Field(ge=0)
    number: int = pydantic.Field(1, ge=1)


class Receipt(CamelModel):
    store: str
    address: str
    date: datetime
    items: list[Item]
    payment: Payment
    client: Optional[Client] = None
    special_offers: Optional[float] = pydantic.Field(None, ge=0)


T = TypeVar("T")


class Envelop(pydantic.generics.GenericModel, Generic[T]):
    __root__: list[T]


def methods(model: Type[CamelModel]) -> Methods:
    envelop = Envelop[model]  # type: ignore

    def serialize_receipts(obj: Envelop[Receipt]):
        for elt in obj.__root__:
            elt.date.isoformat()
        return obj.dict()

    return Methods(
        lambda data: envelop(__root__=data),
        envelop.dict if model is Message else serialize_receipts,
    )


benchmarks = Benchmark(methods(Message), methods(Receipt))
