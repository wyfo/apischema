from dataclasses import (  # type: ignore
    InitVar,
    dataclass,
    field,
    replace as std_replace,
)

from apischema.dataclass_utils import dataclass_types_and_fields
from apischema.dataclasses import replace
from apischema.fields import fields, fields_set, with_fields_set
from apischema.metadata.misc import init_var


@dataclass
class WithInitVar:
    a: InitVar[int] = field(metadata=init_var("int"))


def test_resolve_init_var():
    assert dataclass_types_and_fields(WithInitVar) == (
        {"a": int},
        (),
        (fields(WithInitVar).a,),
    )


@with_fields_set
@dataclass
class WithFieldsSet:
    a: int = 0


def test_replace():
    obj = WithFieldsSet()
    assert fields_set(obj) == set()
    obj2 = std_replace(obj)
    assert fields_set(obj2) == {"a"}
    obj3 = replace(obj)
    assert fields_set(obj3) == set()
