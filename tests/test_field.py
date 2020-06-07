from dataclasses import dataclass, field, fields

from pytest import raises

from apischema.fields import (
    FIELDS_SET_ATTR,
    fields_set,
    set_fields,
    unset_fields,
    with_fields_set,
)
from apischema.utils import get_default


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
    with raises(NotImplementedError):
        get_default(without_default)
    assert get_default(with_default) == 0
    assert get_default(with_default_factory) == 0


def test_fields_set():
    with raises(ValueError):
        fields_set(object())

    assert fields_set(Data(0)) == {"without_default"}
    assert fields_set(Data(without_default=0)) == {"without_default"}
    assert fields_set(Data(0, 1)) == {"without_default", "with_default"}

    data = Data(0)
    data.with_default = 1
    assert fields_set(data) == {"without_default", "with_default"}
    unset_fields(data, "without_default")
    assert fields_set(data) == {"with_default"}
    set_fields(data, "with_default_factory")
    assert fields_set(data) == {"with_default", "with_default_factory"}
    set_fields(data, "with_default", overwrite=True)
    assert fields_set(data) == {"with_default"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    assert fields_set(data) == {
        "without_default",
        "with_default",
        "with_default_factory",
    }
    unset_fields(data, "without_default")
    assert fields_set(data) == {"with_default", "with_default_factory"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    set_fields(data, "with_default")
    assert fields_set(data) == {
        "without_default",
        "with_default",
        "with_default_factory",
    }
    with raises(ValueError):
        set_fields(data, "not_a_field")

    assert fields_set(Inherited(0, other=0)) == {
        "without_default",
        "with_default",
        "with_default_factory",
        "other",
    }
    assert fields_set(DecoratedInherited(0, other=0)) == {
        "without_default",
        "other",
    }
