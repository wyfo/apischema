from json import dumps
from timeit import timeit
from uuid import UUID, uuid4

from apischema import serialization_method

uuids = [uuid4() for i in range(10)]
serialize_uuids = serialization_method(list[UUID])
assert dumps(serialize_uuids(uuids)) == dumps(uuids, default=str)
print(timeit("dumps(serialize_uuids(uuids))", globals=globals()))
# 17.979252214
print(timeit("dumps(uuids, default=str)", globals=globals()))
# 20.795352719000004
