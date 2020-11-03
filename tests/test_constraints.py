from apischema.json_schema.constraints import NumberConstraints, merge_constraints


def test_merge_constraints():
    c1 = NumberConstraints(min=0, max=10)
    c2 = NumberConstraints(min=1, max=5)
    merged = merge_constraints(c1, c2)
    assert merged == NumberConstraints(min=1, max=5)
