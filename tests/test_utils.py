from pytest import raises

from apischema.utils import distinct, to_generator


def test_make_gen():
    def func():
        return 42

    with raises(StopIteration) as err:
        next(iter(to_generator(func)()))
    assert err.value.value == 42


def test_distinct():
    assert list(distinct([4, 0, 1, 0, 4])) == [4, 0, 1]
