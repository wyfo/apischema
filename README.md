# APISchema

Another Python API schema handling and JSON (de)serialization through typing annotation; light, simple, powerful.


## Why another library
Because i'm not satisfied with existing ones. I would like to:
- stay closest as possible to the standard library (dataclasses, etc.) and use it 'as is'
- be able to tune the library and use my own types, instead of having to do a PR for handling of `bson.ObjectId`
- have the least possible dynamic thing (like using string for attribute name)
And I simply want to enjoy myself coding this stuff.


## Getting Started

`pip install apischema` and follow examples (the only *documentation* for now)


## Examples
Following example can be run 'as is' in Python 3.7 (all examples are valid tests of the library).
[quickstart.py](examples/quickstart.py)
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, NewType
from uuid import UUID, uuid4

from pytest import raises

from apischema import (ValidationError, build_input_schema, build_output_schema,
                       from_data, schema, to_data)

Tag = NewType("Tag", str)
schema(title="resource tag", max_len=64)(Tag)


class ResourceType(Enum):
    RESOURCE_A = "A"
    RESOURCE_B = "B"


@dataclass
class Resource:
    id: UUID
    type: ResourceType
    tags: List[Tag] = field(default_factory=list,
                            metadata=schema(max_items=5, unique=True))


def test_resource():
    uuid = uuid4()
    data = {
        "id":   str(uuid),
        "type": "A",
        "tags": ["tag1"]
    }
    resource = from_data(data, Resource)
    assert resource == Resource(uuid, ResourceType.RESOURCE_A, [Tag("tag1")])
    assert to_data(resource) == data
    json_schema = build_input_schema(Resource)
    assert json_schema == build_output_schema(Resource)
    assert to_data(json_schema) == {
        "type":                 "object",
        "required":             ["id", "type"],
        "additionalProperties": False,
        "properties":           {
            "id":   {
                "type":   "string",
                "format": "uuid",
            },
            "type": {
                "type": "string",
                "enum": ["A", "B"],
            },
            "tags": {
                "type":        "array",
                "maxItems":    5,
                "uniqueItems": True,
                "items":       {
                    "type":      "string",
                    "title":     "resource tag",
                    "maxLength": 64,
                },
            },
        }
    }


def test_resource_error():
    with raises(ValidationError) as err:
        from_data({"id": "uuid", "type": None, "tags": ["a", "a"]}, Resource)
    assert err.value == ValidationError(children={
        "id":   ValidationError([
            "[ValueError]badly formed hexadecimal UUID string"
        ]),
        "type": ValidationError([
            "None is not a valid ResourceType"
        ]),
        "tags": ValidationError([
            "duplicates items in ['a', 'a'] (uniqueItems)"
        ])
    })
```
See other [examples](examples); a suggested order:
- [properties.py](examples/properties.py)
- [conversion.py](examples/conversion.py) 
- [validator.py](examples/validator.py) 
- [stringified.py](examples/stringified.py) 
- [generic.py](examples/generic.py) 
- [properties2.py](examples/properties2.py)
- [conversion2.py](examples/conversion2.py) 
- [validator2.py](examples/validator2.py) 
- [recursivity_and_pep563.py](examples/recursivity_and_pep563.py) 
- [generic_conversion.py](examples/generic_conversion.py)
- [raw_conversion.py](examples/raw_conversion.py)


## Benchmark
According to [Pydantic benchmark](https://pydantic-docs.helpmanual.io/benchmarks/), **using only CPython**, *apischema* is a little behind Pydantic, and by toggling some features not provided by *Pydantic* `BaseModel` (`__post_init__`, `patternProperties` at field level) with some optimizations (dataclass fields caching), *apischema* becomes the fastest, ahead of *Pydantic* and others.

Concerning Cython, *apischema* is blocked for now by this [Cython issue](https://github.com/cython/cython/issues/3537)


## Todo
- documentation (obviously)
- tests (coverage is not enough, and edge cases)
- make it work in Python 3.6 (adds dataclass dependency in packaging, checks, etc.)
- optimizations (even if the performances are quite satisfactory)
About formatting and packaging, I'm honestly not interested by the mess of Python regarding theses 20th century issues so I did the minimum. But I know that if the library gains popularity, it will be a mandatory step to dig in it.
