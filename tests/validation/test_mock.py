from dataclasses import dataclass
from typing import ClassVar, cast

from pytest import raises

from apischema.fields import FIELDS_SET_ATTR
from apischema.validation.mock import NonTrivialDependency, ValidatorMock


@dataclass
class Data:
    a: int
    b: str = "1"
    c: ClassVar[int] = 42
    d = 0

    @property
    def property(self) -> int:
        return int(self.b) + self.a

    def method(self, arg: int) -> int:
        return self.a + arg

    @classmethod
    def classmethod(cls, arg: int):
        return cls.c + arg


class SubData(Data):
    pass


def test_mock():
    mock = cast(Data, ValidatorMock(Data, {"a": 0}))
    assert mock.a == 0
    assert mock.b == "1"
    assert mock.c == 42
    assert mock.d == 0
    assert mock.__dict__ == {"a": 0, "b": "1", FIELDS_SET_ATTR: {"a"}}
    assert getattr(mock, FIELDS_SET_ATTR) == {"a"}
    assert mock.property == 1
    assert mock.method(1) == 1
    assert mock.classmethod(0) == 42
    assert mock.__class__ == Data
    assert isinstance(mock, Data)
    assert type(mock) == ValidatorMock
    with raises(NonTrivialDependency):
        _ = mock.e
