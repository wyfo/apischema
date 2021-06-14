from dataclasses import dataclass, field

from pytest import raises

from apischema import ValidationError, dependent_required, deserialize
from apischema.json_schema import deserialization_schema
from apischema.skip import NotNull


@dataclass
class Billing:
    name: str
    # Fields used in dependencies MUST be declared with `field`
    credit_card: NotNull[int] = field(default=None)
    billing_address: NotNull[str] = field(default=None)

    dependencies = dependent_required({credit_card: [billing_address]})


# it can also be done outside the class with
# dependent_required({"credit_card": ["billing_address"]}, owner=Billing)


assert deserialization_schema(Billing) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "additionalProperties": False,
    "dependentRequired": {"credit_card": ["billing_address"]},
    "properties": {
        "name": {"type": "string"},
        "credit_card": {"type": "integer"},
        "billing_address": {"type": "string"},
    },
    "required": ["name"],
    "type": "object",
}

with raises(ValidationError) as err:
    deserialize(Billing, {"name": "Anonymous", "credit_card": 1234_5678_9012_3456})
assert err.value.errors == [
    {
        "loc": ["billing_address"],
        "msg": "missing property (required by ['credit_card'])",
    }
]
