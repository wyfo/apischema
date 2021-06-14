from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, deserialize, validator
from apischema.objects import get_alias, get_field


@dataclass
class BoundedValues:
    # field must be assign to be used, even with empty `field()`
    bounds: tuple[int, int] = field()
    values: list[int]

    # validator("bounds") would also work, but it's not handled by IDE refactoring, etc.
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


# Outside class, fields can still be accessed in a "static" way, to avoid use raw string
@validator(discard=get_field(BoundedValues).bounds)
def bounds_are_sorted_equivalent(bounded: BoundedValues):
    min_bound, max_bound = bounded.bounds
    if min_bound > max_bound:
        yield get_alias(bounded).bounds, "bounds are not sorted"


with raises(ValidationError) as err:
    deserialize(BoundedValues, {"bounds": [10, 0], "values": [-1, 2, 4]})
assert err.value.errors == [
    {"loc": ["bounds"], "msg": "bounds are not sorted"}
    # Without discard, there would have been an other error
    # {"loc": ["values", 1], "msg": "value exceeds bounds"}
]
