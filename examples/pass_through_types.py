from uuid import UUID

from apischema import PassThroughOptions, serialization_method
from apischema.conversions import identity

assert (
    # types is either a collection of types or a type predicate
    serialization_method(UUID, pass_through=PassThroughOptions(types={UUID}))
    == identity
)
