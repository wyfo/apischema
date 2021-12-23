from dataclasses import dataclass
from typing import Collection, Generic, List, Optional, Sequence, TypeVar

import pytest
from _pytest.python_api import raises

from apischema import settings, type_name
from apischema.conversions import Conversion, LazyConversion
from apischema.json_schema import deserialization_schema, serialization_schema
from apischema.json_schema.schema import DeserializationSchemaBuilder
from apischema.type_names import get_type_name
from apischema.typing import Annotated


@type_name(None)
@dataclass
class A:
    a: int


@dataclass
class B:
    a: Optional[A]


type_name("Bs")(List[B])


@type_name("DD")
@dataclass
class D:
    bs: Annotated[List[B], type_name("Bs2")]  # noqa: F821


@dataclass
class Recursive:
    rec: Optional["Recursive"]


def test_find_refs():
    refs = {}
    DeserializationSchemaBuilder.RefsExtractor(
        settings.deserialization.default_conversion, refs
    ).visit(D)
    DeserializationSchemaBuilder.RefsExtractor(
        settings.deserialization.default_conversion, refs
    ).visit(Recursive)
    assert refs == {
        "B": (B, 1),
        "DD": (D, 1),
        "Bs": (Collection[B], 1),
        "Bs2": (Annotated[List[B], type_name("Bs2")], 1),
        "Recursive": (Recursive, 2),
    }


T = TypeVar("T")
U = TypeVar("U")


@dataclass
class DataGeneric(Generic[T]):
    a: T


type_name("StrData")(DataGeneric[str])


@pytest.mark.parametrize("cls", [DataGeneric, DataGeneric[U]])
def test_generic_ref_error(cls):
    with raises(TypeError):
        type_name("Data")(cls)


def test_generic_schema():
    assert deserialization_schema(DataGeneric, all_refs=True) == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "type": "object",
        "properties": {"a": {}},
        "required": ["a"],
        "additionalProperties": False,
    }
    assert deserialization_schema(DataGeneric[int], all_refs=True) == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }
    assert deserialization_schema(DataGeneric[str], all_refs=True) == {
        "$schema": "http://json-schema.org/draft/2020-12/schema#",
        "$ref": "#/$defs/StrData",
        "$defs": {
            "StrData": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
                "additionalProperties": False,
            }
        },
    }


def test_collection_type_name():
    type_name("test")(Sequence[A])
    assert get_type_name(List[A]) == get_type_name(Collection[A]) == ("test", "test")


@type_name(None)
class RecConv:
    pass


def rec_converter(rec: RecConv) -> List[RecConv]:
    ...


def test_recursive_conversion_without_ref():
    tmp = None
    conversion = Conversion(rec_converter, sub_conversion=LazyConversion(lambda: tmp))
    tmp = conversion
    with raises(TypeError, match=r"Recursive type <.*> needs a ref.*"):
        serialization_schema(RecConv, conversion=conversion)
