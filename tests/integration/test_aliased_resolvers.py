from typing import Optional

from graphql import graphql_sync

from apischema.graphql import graphql_schema


def foo(test: int) -> int:
    return test


def bar(my_test: int) -> int:
    return my_test


def baz(my_test: Optional[int]) -> int:
    return my_test or 1


schema = graphql_schema(query=[foo, bar, baz])


def test_no_alias_needed():
    query = """
    {
        foo(test: 4)
    }
    """

    assert graphql_sync(schema, query).data == {"foo": 4}


def test_aliased_parameter():
    query = """
    {
        bar(myTest: 5)
    }
    """

    assert graphql_sync(schema, query).data == {"bar": 5}


def test_aliased_optional_parameter():
    query = """
    {
        baz(myTest: 6)
    }
    """

    assert graphql_sync(schema, query).data == {"baz": 6}
