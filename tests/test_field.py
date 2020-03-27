from dataclasses import InitVar, dataclass, field, fields

from pytest import raises

from apischema import (fields_set, mark_set_fields, unmark_set_fields,
                       with_fields_set)
from apischema.fields import (FIELDS_SET_ATTR, NoDefault, get_default,
                              has_default, init_fields)


@with_fields_set
@dataclass
class Data:
    without_default: int
    with_default: int = 0
    with_default_factory: int = field(default_factory=lambda: 0)


def test_default():
    without_default, with_default, with_default_factory = fields(Data)
    assert not has_default(without_default)
    assert has_default(with_default)
    assert has_default(with_default_factory)

    with raises(NoDefault):
        get_default(without_default)
    assert get_default(with_default) == 0
    assert get_default(with_default_factory) == 0


def test_fields_set():
    with raises(TypeError):
        fields_set(object())

    assert fields_set(Data(0)) == {"without_default"}
    assert fields_set(Data(without_default=0)) == {"without_default"}
    assert fields_set(Data(0, 1)) == {"without_default", "with_default"}

    data = Data(0)
    data.with_default = 1
    assert fields_set(data) == {"without_default", "with_default"}
    unmark_set_fields(data, "without_default")
    assert fields_set(data) == {"with_default"}
    mark_set_fields(data, "with_default_factory")
    assert fields_set(data) == {"with_default", "with_default_factory"}
    mark_set_fields(data, "with_default", overwrite=True)
    assert fields_set(data) == {"with_default"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    assert fields_set(data) == {"without_default", "with_default",
                                "with_default_factory"}
    unmark_set_fields(data, "without_default")
    assert fields_set(data) == {"with_default", "with_default_factory"}
    data.__dict__.pop(FIELDS_SET_ATTR)
    mark_set_fields(data, "with_default")
    assert fields_set(data) == {"without_default", "with_default",
                                "with_default_factory"}
    mark_set_fields(data, "other")
    assert fields_set(data) == {"without_default", "with_default",
                                "with_default_factory", "other"}

    @with_fields_set(init=False)
    class Data2:
        def __init__(self, a: int):
            self.field = a

    assert fields_set(Data2(0)) == {"field"}


@dataclass
class InitData:
    value: int
    init: InitVar[int]
    no_init: int = field(init=False)

    def __post_init__(self, init: int):
        self.no_init = init


def test_init_fields():
    assert [f.name for f in init_fields(InitData)] == ["value", "init"]
    assert [f.name for f in fields(InitData)] == ["value", "no_init"]
