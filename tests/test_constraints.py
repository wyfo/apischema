from apischema.json_schema.constraints import NumberConstraints, merge_constraints


def test_constraint_merging():
    constraints = NumberConstraints(min=1, max=10)
    other = NumberConstraints(min=0, max=5)
    assert merge_constraints(constraints, other) == NumberConstraints(min=1, max=5)
    base_schema = {"minimum": 0, "maximum": 5}
    constraints.merge_into(base_schema)
    assert base_schema == {
        "minimum": 1,
        "maximum": 5,
    }
