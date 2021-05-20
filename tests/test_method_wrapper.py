from apischema.utils import method_wrapper
from apischema.utils import is_async
# from apischema.graphql.resolvers import is_async

class TestClass:
    def foo():
        ...
    
    async def bar():
        ...


def test_sync():    
    wrapper = method_wrapper(TestClass.foo)
    assert not is_async(wrapper)


def test_async():
    wrapper = method_wrapper(TestClass.bar)
    assert is_async(wrapper)
