from src.utils import camelize


def test_camelize():
    assert camelize("one_of") == "oneOf"
