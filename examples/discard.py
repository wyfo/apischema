from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, deserialize, serialize, validator
from apischema.objects import get_alias


@dataclass
class BoundedValues:
    bounds: tuple[int, int] = field()
    values: list[int]

    @validator(discard=bounds)
    def bounds_are_sorted(self):
        min_bound, max_bound = self.bounds
        if min_bound > max_bound:
            yield get_alias(self).bounds, "bounds are not sorted"

    @validator
    def values_dont_exceed_bounds(self):
        min_bound, max_bound = self.bounds
        for index, value in enumerate(self.values):
            if not min_bound <= value <= max_bound:
                yield (get_alias(self).values, index), "value exceeds bounds"


with raises(ValidationError) as err:
    deserialize(BoundedValues, {"bounds": [10, 0], "values": [-1, 2, 4]})
assert serialize(err.value) == [
    {"loc": ["bounds"], "err": ["bounds are not sorted"]}
    # Without discard, there would have been an other error
    # {"loc": ["values", 1], "err": ["value exceeds bounds"]}
]
