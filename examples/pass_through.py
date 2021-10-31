from collections.abc import Collection
from uuid import UUID, uuid4

from apischema import PassThroughOptions, serialization_method

uuids_method = serialization_method(
    Collection[UUID], pass_through=PassThroughOptions(collections=True, types={UUID})
)
uuids = [uuid4() for _ in range(5)]
assert uuids_method(uuids) is uuids
