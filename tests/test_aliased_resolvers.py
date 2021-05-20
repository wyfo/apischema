from dataclasses import dataclass
from unittest.mock import MagicMock

from apischema.graphql.resolvers import (
    resolver_resolve,
    Resolver,
    resolver_parameters,
    resolver,
    _resolvers,
)
from apischema.utils import to_camel_case


@dataclass
class Foo:
    @resolver
    def bar(self, test: int) -> int:
        return test

    @resolver
    def baz(self, my_test: int) -> int:
        return my_test


def test_resolver_no_aliaser_params():
    resolver = _resolvers[Foo]["baz"]
    resolve = resolver_resolve(resolver, {"my_test": int}, lambda x: x)
    assert resolve(Foo(), None, my_test=4) == 4


def test_resolver_no_alias_params():
    resolver = _resolvers[Foo]["bar"]
    resolve = resolver_resolve(resolver, {"test": int}, to_camel_case)
    assert resolve(Foo(), None, test=5) == 5


def test_resolver_with_alias_params():
    resolver = _resolvers[Foo]["baz"]
    resolve = resolver_resolve(resolver, {"my_test": int}, to_camel_case)
    assert resolve(Foo(), None, myTest=7) == 7
