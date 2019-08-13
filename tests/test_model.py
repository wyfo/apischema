from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID as BaseUUID, uuid4

from apischema.model import Model, get_model


class UUID(BaseUUID, Model[str]):
    pass


def test_model():
    assert get_model(UUID) == str

    str_uuid = str(uuid4())
    uuid = UUID.from_model(str_uuid)
    assert uuid == UUID(str_uuid)
    assert uuid.to_model() == str_uuid


T = TypeVar("T")


@dataclass
class TestGeneric(Model[T]):
    field: T

    def to_model(self) -> T:
        return self.field


def test_generic_model():
    assert get_model(TestGeneric) == T

    generic = TestGeneric.from_model(0)
    assert generic == TestGeneric(0)
    assert generic.to_model() == 0
