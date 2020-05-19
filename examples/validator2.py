from dataclasses import dataclass, field
from typing import List, Tuple

from pytest import raises

from apischema import Discard, ValidationError, from_data, get_fields, validator


@dataclass
class Result:
    bounds: Tuple[int, int] = field()
    values: List[int]

    @validator
    def bounds_are_sorted(self):
        min_bound, max_bound = self.bounds
        if min_bound > max_bound:
            fields = get_fields(self)
            yield fields.bounds, "bounds are not sorted"
            raise Discard(fields.bounds)

    @validator(bounds)
    def bounds_are_sorted2(self):  # equivalent to bounds_are_sorted
        min_bound, max_bound = self.bounds
        if min_bound > max_bound:
            yield "bounds are not sorted"

    @validator
    def values_dont_exceed_bounds(self):
        min_bound, max_bound = self.bounds
        for index, value in enumerate(self.values):
            if not min_bound <= value <= max_bound:
                yield index, f"value exceeds bounds"


def test_result():
    data = {
        "bounds": [0, 10],
        "values": [1, 3, 4],
    }
    assert from_data(Result, data) == Result((0, 10), [1, 3, 4])


def test_bad_bounds():
    data = {
        "bounds": [10, 0],
        "values": [1, 3, 4],
    }
    with raises(ValidationError) as err:
        from_data(Result, data)
    assert err.value == ValidationError(children={
        "bounds": ValidationError(["bounds are not sorted"])
    })


def test_bad_values():
    data = {
        "bounds": [0, 10],
        "values": [1, 3, -4, 4, 42],
    }
    with raises(ValidationError) as err:
        from_data(Result, data)
    assert err.value == ValidationError(children={
        "2": ValidationError(["value exceeds bounds"]),
        "4": ValidationError(["value exceeds bounds"]),
    })
