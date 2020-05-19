from apischema.utils import distinct


def test_distinct():
    assert list(distinct([4, 0, 1, 0, 4])) == [4, 0, 1]
