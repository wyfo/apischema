from pytest import mark, raises

from apischema.validation.dependencies import find_all_dependencies, find_dependencies


def a_equal_b(param):
    assert param.a == param.b


@mark.parametrize("func, deps", [(a_equal_b, {"a", "b"}), (int, set())])
def test_find_dependencies(func, deps):
    assert find_dependencies(func) == deps


def test_no_parameter():
    with raises(TypeError):
        find_dependencies(lambda: None)


def test_find_end_dependencies():
    class Test:
        class_var = ""

        def __init__(self):
            self.a = 0
            self.b = {}

        def pseudo_validate(self):
            if self.a not in self.method(0):
                yield self.class_var

        def method(self, arg):
            res = list(self.c)
            if len(res) < arg:
                return self.method(arg - 1)

        @property
        def c(self):
            return self.b.values()

    assert find_all_dependencies(Test, Test.pseudo_validate) == {"a", "b", "class_var"}
