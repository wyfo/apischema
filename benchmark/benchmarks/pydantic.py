from datetime import datetime
from typing import Optional, Type

import pydantic
from common import Benchmark, Methods, Payment, to_camel_case


class CamelModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(alias_generator=to_camel_case)


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


def methods(model: Type[CamelModel]) -> Methods:
    def serialize_receipts(obj: Receipt):
        obj.date.isoformat()
        return obj.model_dump()

    return Methods(
        lambda data: model(**data),
        model.model_dump if model is Message else serialize_receipts,
    )


benchmarks = Benchmark(methods(Message), methods(Receipt))
