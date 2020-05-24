from dataclasses import asdict, dataclass
from typing import Any

from apischema.utils import (
    GeneratorValue,
    NO_DEFAULT,
    as_dict,
    to_camel_case,
    to_hashable,
)


def test_to_hashable():
    hashable1 = to_hashable({"key1": 0, "key2": [1, 2]})
    hashable2 = to_hashable({"key2": [1, 2], "key1": 0})
    assert hashable1 == hashable2
    assert hash(hashable1) == hash(hashable2)


def test_generator_value():
    def generator():
        yield 0
        return 1

    value = GeneratorValue(generator())
    assert list(value) == [0]
    assert value.value == 1


def test_to_camel_case():
    assert to_camel_case("min_length") == "minLength"


@dataclass
class Data:
    default: Any = NO_DEFAULT


def test_as_dict():
    assert as_dict(Data()) == {"default": NO_DEFAULT}
    assert asdict(Data()) != {"default": NO_DEFAULT}  # because of deepcopy ...
