from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from timeit import timeit
from typing import Any
from uuid import UUID, uuid4

import orjson  # used in timeit  # noqa

from apischema import PassThroughOptions, serialization_default, serialization_method


class State(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class Data:
    id: UUID
    state: State
    tags: Collection[str]
    extra: Any


# orjson supports enums (by values), dataclasses and UUID natively
pass_through = PassThroughOptions(
    any=True, enums=True, collections=True, dataclasses=True, types={UUID}
)
serialize_data = serialization_method(Data, pass_through=pass_through)
default = serialization_default()
serialize_data2 = serialization_method(Data)  # no pass_through

data = Data(uuid4(), State.ACTIVE, ["foo", "bar"], {"answer": 42})
assert serialize_data(data) is data  # data is passed through

print(timeit("orjson.dumps(serialize_data(data), default=default)", globals=globals()))
# 1.248541576
print(timeit("orjson.dumps(serialize_data2(data))", globals=globals()))
# 4.826223127 ~ 4x slower without pass_through
