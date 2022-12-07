import pytest

from apischema.serialization import IntMethod, TupleMethod


def test_tuple_conversion() -> None:
    method = TupleMethod(elt_methods=(IntMethod(), IntMethod(), IntMethod()))

    with pytest.raises(ValueError):
        method.serialize((0, 0, 0, 0))
