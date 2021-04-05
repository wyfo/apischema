import bson
from pytest import raises

from apischema import Unsupported, deserialize, serialize
from apischema.conversions import as_str

with raises(Unsupported):
    deserialize(bson.ObjectId, "0123456789ab0123456789ab")
with raises(Unsupported):
    serialize(bson.ObjectId("0123456789ab0123456789ab"))

as_str(bson.ObjectId)

assert deserialize(bson.ObjectId, "0123456789ab0123456789ab") == bson.ObjectId(
    "0123456789ab0123456789ab"
)
assert (
    serialize(bson.ObjectId("0123456789ab0123456789ab")) == "0123456789ab0123456789ab"
)
