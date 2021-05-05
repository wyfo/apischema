from dataclasses import dataclass

from pytest import raises

from apischema import Undefined, ValidationError, alias, deserialize, schema, serialize
from apischema.tagged_unions import Tagged, TaggedUnion, get_tagged


@dataclass
class Bar:
    field: str


class Foo(TaggedUnion):
    bar: Tagged[Bar]
    # Tagged can have metadata like a dataclass fields
    i: Tagged[int] = Tagged(alias("baz") | schema(min=0))


# Instantiate using class fields
tagged_bar = Foo.bar(Bar("value"))
# you can also use default constructor, but it's not typed-checked
assert tagged_bar == Foo(bar=Bar("value"))

# All fields that are not tagged are Undefined
assert tagged_bar.bar is not Undefined and tagged_bar.i is Undefined
# get_tagged allows to retrieve the tag and it's value
# (but the value is not typed-checked)
assert get_tagged(tagged_bar) == ("bar", Bar("value"))

# (De)serialization works as expected
assert deserialize(Foo, {"bar": {"field": "value"}}) == tagged_bar
assert serialize(tagged_bar) == {"bar": {"field": "value"}}

with raises(ValidationError) as err:
    deserialize(Foo, {"unknown": 42})
assert serialize(err.value) == [{"loc": ["unknown"], "err": ["unexpected property"]}]

with raises(ValidationError) as err:
    deserialize(Foo, {"bar": {"field": "value"}, "baz": 0})
assert serialize(err.value) == [
    {"loc": [], "err": ["size greater than 1 (maxProperties)"]}
]
