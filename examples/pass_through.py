from collections.abc import Collection
from uuid import UUID

from apischema import PassThroughOptions, serialization_method
from apischema.conversions import identity

uuids_method = serialization_method(
    Collection[UUID], pass_through=PassThroughOptions(collections=True, types={UUID})
)
assert uuids_method == identity
