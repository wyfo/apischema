from dataclasses import dataclass, field, fields

from pytest import raises

from apischema import (
    get_fields_set,
    mark_set_fields,
    unmark_set_fields,
    with_fields_set,
)
from apischema.fields import FIELDS_SET_ATTR, NoDefault, get_default


@with_fields_set
@dataclass
class Data:
    without_default: int
    with_default: int = 0
    with_default_factory: int = field(default_factory=lambda: 0)


@dataclass
class Inherited(Data):
    other: int = 42


@with_fields_set
@dataclass
class DecoratedInherited(Data):
    other: int = 42


def test_default():
    without_default, with_default, with_default_factory = fields(Data)
    with raises(NoDefault):
        get_default(without_default)
    assert get_default(with_default) == 0
    assert get_default(with_default_factory) == 0


def test_fields_set():
    with raises(ValueError):
        get_fields_set(object())

    assert get_fields_set(Data(0)) == {"without_default"}
    assert get_fields_set(Data(without_default=0)) == {"without_default"}
    assert get_fields_set(Data(0, 1)) == {"without_default", "with_default"}

    data = Data(0)
    data.with_default = 1
    assert get_fields_set(data) == {"without_default", "with_default"}
    unmark_set_fields(data, "without_default")
    assert get_fields_set(data) == {"with_default"}
    mark_set_fields(data, "with_default_factory")
    assert get_fields_set(data) == {"with_default", "with_default_factory"}
    mark_set_fields(data, "with_default", overwrite=True)
    assert get_fields_set(data) == {"with_default"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    assert get_fields_set(data) == {
        "without_default",
        "with_default",
        "with_default_factory",
    }
    unmark_set_fields(data, "without_default")
    assert get_fields_set(data) == {"with_default", "with_default_factory"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    mark_set_fields(data, "with_default")
    assert get_fields_set(data) == {
        "without_default",
        "with_default",
        "with_default_factory",
    }
    with raises(ValueError):
        mark_set_fields(data, "not_a_field")

    assert get_fields_set(Inherited(0, other=0)) == {
        "without_default",
        "with_default",
        "with_default_factory",
        "other",
    }
    assert get_fields_set(DecoratedInherited(0, other=0)) == {
        "without_default",
        "other",
    }
