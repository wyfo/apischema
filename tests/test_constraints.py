from apischema.json_schema.constraints import NumberConstraints


def test_merge_constraints():
    c1 = NumberConstraints(minimum=0, maximum=10)
    c2 = NumberConstraints(minimum=1, maximum=5)
    merged = c1.merge(c2)
    assert merged == NumberConstraints(minimum=1, maximum=5)
    assert c1.merge(c2) is merged
