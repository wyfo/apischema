from dataclasses import dataclass
from typing import Annotated, Literal, Union

import pytest

from apischema import deserialize, discriminator, serialize
from apischema.json_schema import deserialization_schema
from apischema.typing import TypedDict


class TypedDictWithoutField(TypedDict):
    pass


class TD1(TypedDict):
    type: str


class TD2(TypedDict):
    type: str


def test_typed_dict_without_discriminator_field_cannot_have_discriminator():
    with pytest.raises(TypeError):
        deserialization_schema(
            Annotated[Union[TD1, TypedDictWithoutField], discriminator("type")]
        )


def test_typed_dict_discriminator():
    assert deserialize(
        Annotated[Union[TD1, TD2], discriminator("type")], {"type": "TD1"}
    ) == {"type": "TD1"}
    assert serialize(
        Annotated[Union[TD1, TD2], discriminator("type")], {"type": "TD1"}
    ) == {"type": "TD1"}


@dataclass
class A:
    type: Literal["a"]


@dataclass
class B:
    pass


@pytest.mark.parametrize("type_, obj", [("a", A("a")), ("b", B())])
def test_discriminator_literal_field(type_, obj):
    assert (
        deserialize(Annotated[Union[A, B], discriminator("type")], {"type": type_})
        == obj
    )
    assert serialize(Annotated[Union[A, B], discriminator("type")], obj) == {
        "type": type_
    }
