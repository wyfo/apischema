# APISchema

Another Python API schema handling through typing annotation; light, simple, powerful.

## Getting Started

This README is a draft.
The project is not yet available on Pypi. You can still clone the project to use it.
Run the tests with *tox*.

## Examples

Simple example:
```Python
import json
import uuid
from dataclasses import dataclass
from typing import Iterator, Sequence

from src.data import from_data, to_data
from src.model import Model
from src.schema import build_schema
from src.validator import Error, validate


class UUID(Model[str], uuid.UUID):
    pass


@dataclass
class MyModel:
    id: UUID
    elts: Sequence[int]
    check_sum: int

    @validate("elts", "check_sum")
    def elts_sum(self) -> Iterator[Error]:
        if sum(self.elts) != self.check_sum:
            yield "check_sum doesn't match elts"


data = json.load(...) # type: ignore
# data = {"id": str(uuid4()), "elts": [1, 2], "check_sum": 3} 
my_model = from_data(MyModel, data, camel_case=False)
data2 = to_data(MyModel, my_model, camel_case=False)

openapi = build_schema(MyModel, camel_case=False)
```

A little bit more complex
```Python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, TypeVar, Union, Iterator, Generic

import pytest

from src.data import from_data
from src.model import Model
from src.validation import ValidationError
from src.validator import Error, validate

T = TypeVar("T")


class A(Model[Union[T, List[T]]], List[T]):
    @classmethod
    def from_model(cls, obj: Union[T, List[T]]) -> A:
        if isinstance(obj, list):
            return A(obj)
        else:
            return A([obj])

    def to_model(self) -> Union[T, List[T]]:
        return self[0] if len(self) == 1 else list(self)

    @validate
    def no_consecutive_duplicates(self) -> Iterator[Error]:
        if len(self) == 0:
            return
        cur = self[0]
        for i in range(1, len(self)):
            if cur == self[i]:
                yield f"duplicate elt {cur} in position {i}"
            cur = self[i]


@dataclass
class B(Generic[T]):
    a: A[T] = field(default_factory=A)


def test():
    print()
    print(from_data(B, {}))
    print(from_data(B[int], {}))
    print(from_data(B[int], {"a": 0}))
    print(from_data(B[int], {"a": [1, 2]}))
    with pytest.raises(ValidationError) as err:
        print(from_data(B[int], {"a": [1, 2, 2]}))
    print(err.value)
    with pytest.raises(ValidationError) as err:
        print(from_data(B[str], {"a": ["", 0, 1]}))
    print(err.value)

```

With *spec*:
```Python
from dataclasses import dataclass

from src.data import from_data, to_data
from src.field import field
from src.model import Model
from src.schema import Schema, build_schema
from src.spec import NumSpec, SpecClass


class ShortString(Model[str], SpecClass, str):
    max_length = 10


@dataclass
class A:
    positive: int = field(spec=NumSpec(min=0))
    short_string: ShortString = ShortString("")


def test():
    # data = json.load(...)
    data = {"positive": 1, "shortString": "ok"}
    a = from_data(A, data)
    data2 = to_data(A, a)
    print(data2)

    openapi = build_schema(A)
    print(to_data(Schema, openapi))

```
