import dataclasses
from dataclasses import Field
from unittest.mock import Mock

from src.field import field, get_aliased, get_default, has_default


def test_field():
    f = field(mock=Mock())
    assert isinstance(f, Field)


def test_default():
    with_default = dataclasses.field(default=0)
    assert has_default(with_default) and get_default(with_default) == 0
    with_default_factory = dataclasses.field(default_factory=list)
    assert has_default(with_default_factory) and \
           get_default(with_default_factory) == []
    assert not has_default(dataclasses.field())


def test_aliased():
    assert get_aliased(field(alias="alias")) == "alias"
    f = dataclasses.field()
    f.name = "name"
    assert get_aliased(f) == "name"
