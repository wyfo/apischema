from contextlib import nullcontext
from typing import Iterable
from unittest.mock import Mock

from pytest import fixture, mark, raises

from apischema.validation import Validation, ValidationError
from apischema.validator import Error


@fixture
def validation() -> Validation:
    return Validation()


@mark.parametrize("error, additional_path", [
    ("error", ()),
    (("other", "error"), ("other",)),
    ((("other",), "error"), ("other",)),
])
def test_report(validation, error, additional_path):
    path = ("path",)
    validation.report(path, error)
    assert validation.errors == [((*path, *additional_path,), "error")]


def raising_errors() -> Iterable[Error]:
    yield from ()
    raise Exception("error")


@mark.parametrize("errors, expected, result", [
    ([], False, []),
    (["error1", "error2", ("path", "error3")], True, [
        ((), "error1"), ((), "error2"), (("path",), "error3")
    ]),
    (raising_errors(), True, [((), "error")])
])
def test_report_many(validation, errors, expected, result):
    assert validation.report_many((), errors) == expected
    assert validation.errors == result


@mark.parametrize("ctx, cls, data", [
    (nullcontext(), int, 0),
    (nullcontext(), list, [0, ""]),
    (raises(ValidationError), int, "")
])
def test_check_type(validation, ctx, cls, data):
    with ctx:
        validation.check_type((), data, cls)


def test_validation_error_asdict(validation):
    path = ("key1",)
    validation.report(path, "error1")
    validation.report(path, "error2")
    validation.report(path, ("key2", "error3"))
    path = ()
    validation.report(path, "error4")
    validation.report(path, "error5")
    assert ValidationError(validation).asdict == {
        ():               ["error4", "error5"],
        ("key1",):        ["error1", "error2"],
        ("key1", "key2"): ["error3"]
    }


def test_merge(validation):
    path = ("key",)
    with validation.tmp_errors() as alt1:
        validation.report(path, "error1")
    path = ()
    with validation.tmp_errors() as alt2:
        validation.report(path, "error2")
    assert validation.errors == []
    validation.merge(alt1, alt2)
    assert validation.errors == [(("key",), "error1"), ((), "error2")]


@mark.parametrize("validators, error", [
    ([Mock(return_value=[]), Mock(return_value=[])], False),
    ([Mock(return_value=[]), Mock(return_value=["error"])], True),
])
def test_validate(validation, validators, error):
    ctx = raises(ValidationError) if error else nullcontext()
    with ctx:
        validation.validate((), validators, Mock())
