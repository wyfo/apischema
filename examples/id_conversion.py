from base64 import b64decode, b64encode
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from graphql import graphql_sync

from apischema.graphql import graphql_schema


@dataclass
class Foo:
    id: UUID


def foo() -> Optional[Foo]:
    return Foo(UUID("58c88e87-5769-4723-8974-f9ec5007a38b"))


schema = graphql_schema(
    query=[foo],
    id_types={UUID},
    id_encoding=(
        lambda s: b64decode(s).decode(),
        lambda s: b64encode(s.encode()).decode(),
    ),
)

assert graphql_sync(schema, "{foo{id}}").data == {
    "foo": {"id": "NThjODhlODctNTc2OS00NzIzLTg5NzQtZjllYzUwMDdhMzhi"}
}
