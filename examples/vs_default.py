from json import dumps
from timeit import timeit
from uuid import UUID, uuid4

from apischema import PassThroughOptions, serialization_default, serialization_method

uuids = [uuid4() for i in range(10)]
serialize_uuids = serialization_method(list[UUID])
serialize_uuids2 = serialization_method(
    list[UUID], pass_through=PassThroughOptions(types={UUID})
)
default = serialization_default()
assert (
    dumps(serialize_uuids(uuids))
    == dumps(serialize_uuids2(uuids), default=default)
    == dumps(uuids, default=str)  # equivalent to previous one, but faster
)
print(timeit("dumps(serialize_uuids(uuids))", globals=globals()))
# 18.171754636
print(timeit("dumps(uuids, default=str)", globals=globals()))
# 21.188269333
print(timeit("dumps(serialize_uuids2(uuids), default=default)", globals=globals()))
# 24.494076885
