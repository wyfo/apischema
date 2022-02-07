from dataclasses import dataclass, field

import pytest

from apischema import (
    Undefined,
    UndefinedType,
    ValidationError,
    dependent_required,
    deserialize,
)
from apischema.json_schema import deserialization_schema


@dataclass
class Billing:
    name: str
    # Fields used in dependencies MUST be declared with `field`
    credit_card: int | UndefinedType = field(default=Undefined)
    billing_address: str | UndefinedType = field(default=Undefined)

    dependencies = dependent_required({credit_card: [billing_address]})


# it can also be done outside the class with
# dependent_required({"credit_card": ["billing_address"]}, owner=Billing)


assert deserialization_schema(Billing) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
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

with pytest.raises(ValidationError) as err:
    deserialize(Billing, {"name": "Anonymous", "credit_card": 1234_5678_9012_3456})
assert err.value.errors == [
    {
        "loc": ["billing_address"],
        "err": "missing property (required by ['credit_card'])",
    }
]
