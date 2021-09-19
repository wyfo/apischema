from typing import NewType

from apischema import deserialize, serialize
from apischema.conversions import Conversion

Int = NewType("Int", int)


def test_new_type_conversion():
    assert (
        deserialize(Int, "0", conversion=Conversion(int, source=str, target=Int)) == 0
    )
    assert serialize(Int, 0, conversion=Conversion(str, source=Int)) == "0"
