from pytest import mark, raises

from src.model import Model
from src.spec import (ArraySpec, NumSpec, ObjectSpec, Spec, SpecClass, StrSpec,
                      get_spec, spec_from_dict)


def test_spec_validators():
    assert list(Spec().validator({})) == []


@mark.parametrize("cls, field, value, correct, error", [
    (NumSpec, "min", 0, 0, -1),
    (NumSpec, "max", 0, 0, 1),
    (NumSpec, "exc_min", 0, 1, 0),
    (NumSpec, "exc_max", 0, -1, 0),
    (NumSpec, "multiple_of", 2, 4, 5),
    (StrSpec, "min_length", 2, "ok", "k"),
    (StrSpec, "max_length", 2, "ok", "oki"),
    (StrSpec, "pattern", "a.*c", "abc", "ab"),
    (ArraySpec, "min_items", 2, [0, 1], []),
    (ArraySpec, "max_items", 2, [0, 1], [0, 1, 2]),
    (ObjectSpec, "min_properties", 2, {"a": 0, "b": 1}, {}),
    (ObjectSpec, "max_properties", 2, {"a": 0, "b": 1},
     {"a": 0, "b": 1, "c": 2}),
])
def test_other_validators(cls, field, value, correct, error):
    # noinspection PyArgumentList
    spec = cls(**{field: value})
    assert not bool(list(spec.validator(correct)))
    assert bool(list(spec.validator(error)))


class SmallInt(SpecClass, Model[int]):
    example = 2
    max = 10


class Example(SpecClass, Model[str]):
    title_ = "simple string"
    example = "string"


@mark.parametrize("cls, expected", [
    (SmallInt, NumSpec(example=2, max=10)),
    (Example, Spec(title="simple string", example="string")),
])
def test_spec_from_dict(cls, expected):
    assert spec_from_dict(cls.__dict__) == expected


def test_spec_from_dict_error():
    with raises(ValueError):
        spec_from_dict({"min": 0, "pattern": ""})


class WithSpecAsAttribute:
    spec = Spec(title="simple string", example="string")


class WithoutSpec:
    pass


def test_get_spec():
    expected = Spec(title="simple string", example="string")
    assert get_spec(Example) == get_spec(WithSpecAsAttribute) == expected
    assert get_spec(WithoutSpec) is None
