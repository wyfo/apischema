from dataclasses import dataclass
from typing import Union

from pytest import raises
from typing_extensions import Annotated

from apischema import ValidationError, deserialize, serialize
from apischema.types import Skip


@dataclass
class Foo:
    # by the way NotNull = Optional[T, Annotated[None, Skip]]
    bar: Union[int, Annotated[None, Skip]] = None


with raises(ValidationError) as err:
    deserialize(Foo, {"bar": None})
assert serialize(err.value) == [
    {"loc": ["bar"], "err": ["expected type integer, found null"]}
]
