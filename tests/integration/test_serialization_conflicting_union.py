from dataclasses import dataclass
from typing import Union, Tuple

import apischema


@dataclass(frozen=True)
class SomeTupleClass:
    bar: Union[Tuple[int, int], Tuple[int, int, int]]


def test_correct_serialization() -> None:
    serialized_dict = {
        "bar": [0, 0, 0]
    }

    as_python_object = apischema.deserialize(type=SomeTupleClass, data=serialized_dict)

    assert as_python_object == SomeTupleClass(bar=(0, 0, 0))

    assert apischema.serialize(as_python_object) == serialized_dict
