from uuid import UUID as BaseUUID

import humps
from pytest import mark

from apischema.model import Model
from apischema.visitor import Visitor, camel_case_aliaser


def test_camel_case_aliaser():
    assert camel_case_aliaser(False) is None
    assert camel_case_aliaser(True) is humps.camelize


@mark.parametrize("s", ["", "name", "snake_case", "camelCase"])
def test_visitor_default_aliaser(s):
    visitor = Visitor(None)
    assert visitor.aliaser(s) == s


class UUID(BaseUUID, Model[str]):
    pass


@mark.parametrize("cls, expected", [
    (int, None),
    (Model, Model),
    (UUID, UUID),
])
def test_visitor_is_custom(cls, expected):
    assert Visitor(None).is_custom(cls, None) == expected
