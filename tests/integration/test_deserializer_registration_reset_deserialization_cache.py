import pytest

from apischema import ValidationError, deserialize, deserializer
from apischema.conversions import Conversion, catch_value_error


class Foo(int):
    pass


def test_deserializer_registration_reset_deserialization_cache():
    assert deserialize(Foo, 1) == Foo(1)
    deserializer(Conversion(catch_value_error(Foo), source=str, target=Foo))
    assert deserialize(Foo, "1") == Foo(1)
    with pytest.raises(ValidationError):
        deserialize(Foo, 1)
