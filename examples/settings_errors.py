from pytest import raises

from apischema import ValidationError, deserialize, schema, settings

settings.errors.max_items = (
    lambda constraint, data: f"too-many-items: {len(data)} > {constraint}"
)


with raises(ValidationError) as err:
    deserialize(list[int], [0, 1, 2, 3], schema=schema(max_items=3))
assert err.value.errors == [{"loc": [], "msg": "too-many-items: 4 > 3"}]
