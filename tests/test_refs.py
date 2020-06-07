from dataclasses import dataclass
from typing import List, Optional

from apischema import schema_ref
from apischema.json_schema.generation.builder import DeserializationSchemaBuilder
from apischema.typing import Annotated


@schema_ref(None)
@dataclass
class A:
    a: int


@dataclass
class B:
    a: Optional[A]


schema_ref("Bs")(List[B])


@schema_ref("DD")
@dataclass
class D:
    bs: Annotated[List[B], schema_ref("Bs2")]  # noqa F821


@dataclass
class Recursive:
    rec: Optional["Recursive"]


def test_find_refs():
    refs = {}
    DeserializationSchemaBuilder.RefsExtractor(None, refs).visit(D)
    DeserializationSchemaBuilder.RefsExtractor(None, refs).visit(Recursive)
    assert refs == {
        "B": (B, 1),
        "DD": (D, 1),
        "Bs": (List[B], 1),
        "Bs2": (Annotated[List[B], schema_ref("Bs2")], 1),
        "Recursive": (Recursive, 2),
    }
