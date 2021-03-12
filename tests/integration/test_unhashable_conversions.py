from dataclasses import dataclass

from graphql import graphql_sync

from apischema import deserialize, serialize
from apischema.graphql import Query, graphql_schema, resolver
from apischema.json_schema import deserialization_schema, serialization_schema


@dataclass
class Foo:
    @resolver(conversions=[], serialized=True)
    def bar(self) -> int:
        return 0


def foo() -> Foo:
    return Foo()


def test_unhashable_conversions():
    deserialize(int, 0, conversions=[])
    serialize(Foo(), conversions=[])
    deserialization_schema(Foo, conversions=[])
    serialization_schema(Foo, conversions=[])
    schema = graphql_schema(query=[Query(foo, conversions=[])])
    graphql_sync(schema, "{ foo { bar } }")
