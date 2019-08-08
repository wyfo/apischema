from dataclasses import dataclass, fields
from inspect import getmembers
from re import fullmatch
from typing import Any, Mapping, Optional, Type, TypeVar, Union, cast

from src.validator import ValidationResult, Validator

SPEC_FIELD = "__spec__"

Number = Union[int, float]


@dataclass
class Spec:
    title: Optional[str] = None
    description: Optional[str] = None
    example: Optional[Any] = None

    @property
    def validator(self) -> Validator:
        def validate(_: Any) -> ValidationResult:
            yield from ()

        return Validator(validate)


@dataclass
class NumSpec(Spec):
    min: Optional[Number] = None
    max: Optional[Number] = None
    exc_min: Optional[Number] = None
    exc_max: Optional[Number] = None
    multiple_of: Optional[Number] = None

    def __post_init__(self):
        assert self.min is None or self.exc_min is None
        assert self.max is None or self.exc_max is None
        if self.min is not None:
            assert self.max is None or self.max >= self.min
            assert self.exc_max is None or self.exc_max > self.min
        if self.exc_min is not None:
            assert self.max is None or self.max > self.exc_min
            assert self.exc_max is None or self.exc_max > self.exc_min

    @property
    def validator(self) -> Validator:
        def validate(data: Any) -> ValidationResult:
            assert isinstance(data, int) or isinstance(data, float)
            if self.min is not None and data < self.min:
                yield f"{data} < {self.min} (minimum)"
            if self.max is not None and data > self.max:
                yield f"{data} > {self.max} (maximum)"
            if self.exc_min is not None and data <= self.exc_min:
                yield f"{data} <= {self.min} (exclusiveMinimum)"
            if self.exc_max is not None and data >= self.exc_max:
                yield f"{data} >= {self.max} (exclusiveMaximum)"
            if self.multiple_of is not None and (data % self.multiple_of) != 0:
                yield f"{data} if not a multiple of " \
                    f"{self.multiple_of} (multipleOf)"

        return Validator(validate)


@dataclass
class StrSpec(Spec):
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None

    @property
    def validator(self) -> Validator:
        def validate(data: Any) -> ValidationResult:
            assert isinstance(data, str)
            if self.min_length and len(data) < self.min_length:
                yield f"'{data}'.length < {self.min_length} (minLength)"
            if self.max_length and len(data) > self.max_length:
                yield f"'{data}'.length > {self.max_length} (maxLength)"
            if self.pattern is not None and not fullmatch(self.pattern, data):
                yield f"'{data}' does not match '{self.pattern}' pattern"

        return Validator(validate)


@dataclass
class ArraySpec(Spec):
    min_items: Optional[int] = None
    max_items: Optional[int] = None

    @property
    def validator(self) -> Validator:
        def validate(data: Any) -> ValidationResult:
            assert isinstance(data, list)
            if self.min_items and len(data) < self.min_items:
                yield f"not enough items, {len(data)} is lower than " \
                    f"{self.min_items} (minItems)"
            if self.max_items and len(data) > self.max_items:
                yield f"too much items, {len(data)} is greater than " \
                    f"{self.max_items} (maxItems)"

        return Validator(validate)


@dataclass
class ObjectSpec(Spec):
    min_properties: Optional[int] = None
    max_properties: Optional[int] = None

    @property
    def validator(self) -> Validator:
        def validate(data: Any) -> ValidationResult:
            assert isinstance(data, dict)
            if self.min_properties and len(data) < self.min_properties:
                yield f"not enough properties, {len(data)} is lower than " \
                    f"{self.min_properties} (minProperties)"
            if self.max_properties and len(data) > self.max_properties:
                yield f"too much properties, {len(data)} is greater than " \
                    f"{self.max_properties} (maxProperties)"

        return Validator(validate)


Arg = TypeVar("Arg")


class SpecClass:
    title_: Optional[str] = None  # can mix up with str.title
    description: Optional[str] = None
    example: Optional[Any] = None
    min: Optional[Number] = None
    max: Optional[Number] = None
    exc_min: Optional[Number] = None
    exc_max: Optional[Number] = None
    multiple_of: Optional[Number] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    min_properties: Optional[int] = None
    max_properties: Optional[int] = None


def spec_from_dict(spec: Mapping[str, Any]) -> Spec:
    if "title_" in spec and "title" not in spec:
        spec = dict(spec)
        spec["title"] = spec.pop("title_")
    simple_spec_fields = {f.name for f in fields(Spec)}
    match = []
    for spec_cls in (NumSpec, StrSpec, ArraySpec, ObjectSpec):
        for field in fields(spec_cls):
            if field.name not in simple_spec_fields and \
                    spec.get(field.name, None) is not None:
                match.append(spec_cls)
    if len(match) > 1:
        raise ValueError(f"Overlapping specifications with attributes "
                         f"{[*spec]}")
    cls = match[0] if match else Spec
    return cls(**{field.name: spec.get(field.name, None)
                  for field in fields(cls)})


def get_spec(cls: Type) -> Optional[Spec]:
    if hasattr(cls, SPEC_FIELD):
        return getattr(cls, SPEC_FIELD)
    if issubclass(cls, SpecClass):
        return spec_from_dict(cls.__dict__)
    spec = getmembers(cls, predicate=lambda m: isinstance(m, Spec))
    res = cast(Spec, getattr(cls, spec[0][0])) if spec else None
    setattr(cls, SPEC_FIELD, res)
    return res
