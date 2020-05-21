# APISchema

Another Python API schema handling and JSON (de)serialization through typing annotation; light, simple, powerful.


## Why another library
Because i'm not satisfied with existing ones. I would like to:
- stay closest as possible to the standard library (dataclasses, typing, etc.), and as a consequency to have no need of plugin for editor/linter/etc.
- be able to tune the library and use my own types (or foreign libraries ones), instead of having to do a PR for handling of `bson.ObjectId`
- have the least possible dynamic thing (like using string for attribute name)
And I simply want to enjoy myself coding this stuff.


## Getting Started

`pip install apischema` and follow examples (the only *documentation* for now)


## Examples
Following example can be run 'as is' in Python 3.7 (all examples are valid tests of the library).
[quickstart.py](examples/example_quickstart.py)
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
    resource = from_data(Resource,data)
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
        from_data(Resource,{"id": "uuid", "type": None, "tags": ["a", "a"]})
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
- [example_properties.py](examples/example_properties.py)
- [example_conversion.py](examples/example_conversion.py) 
- [example_validator.py](examples/example_validator.py) 
- [example_coercion.py](examples/example_coercion.py) 
- [example_generic.py](examples/example_generic.py) 
- [example_properties2.py](examples/example_properties2.py)
- [example_conversion2.py](examples/example_conversion2.py) 
- [example_validator2.py](examples/example_validator2.py) 
- [example_recursivity_and_pep563.py](examples/example_recursivity_and_pep563.py) 
- [example_generic_conversion.py](examples/example_generic_conversion.py)
- [example_raw_conversion.py](examples/example_raw_conversion.py)


## Benchmark
Using [Pydantic benchmark](https://pydantic-docs.helpmanual.io/benchmarks/), **using only CPython**, *apischema* is faster than others libraries, including *Pydantic*, present in the benchmark.

Concerning Cython, *apischema* is blocked for now by this [Cython issue](https://github.com/cython/cython/issues/3537)


## Todo
- documentation (obviously)
- tests (coverage is not enough, and edge cases)
- make it work in Python 3.6 (adds dataclass dependency in packaging, checks, etc.)

About formatting and packaging, I'm honestly not interested by the mess of Python regarding theses 20th century issues so I did the minimum. But I know that if the library gains popularity, it will be a mandatory step to dig in it.
