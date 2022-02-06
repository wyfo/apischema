from apischema.constraints import merge_constraints
from apischema.schemas import Constraints


def test_constraint_merging():
    constraints = Constraints(min=1, max=10)
    other = Constraints(min=0, max=5)
    assert merge_constraints(constraints, other) == Constraints(min=1, max=5)
    base_schema = {"minimum": 0, "maximum": 5}
    constraints.merge_into(base_schema)
    assert base_schema == {"minimum": 1, "maximum": 5}
