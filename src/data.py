from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import (Any, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Type, TypeVar, get_type_hints)

from src.errors import (MISSING_FIELD, UNION_PATH, WRONG_LITERAL, WRONG_TYPE)
from src.field import NoDefault, get_aliased, get_default
from src.model import Model, get_model
from src.null import null_values, set_null_values
from src.spec import Spec, get_spec
from src.types import Primitive, is_resolved, resolve_types, type_name
from src.utils import camelize
from src.validation import Errors, Validation, ValidationError
from src.validator import PartialValidator, ValidatorMock, validators
from src.visitor import Path, Visitor


class FromData(Visitor[Any, Any], Validation):
    def __init__(self, camel_case=True, spec_key="spec"):
        Visitor.__init__(self)
        Validation.__init__(self)
        self.camel_case = camel_case
        self.spec_key = spec_key

    def with_class_context(self, cls: Type, data: Any, path: Path) -> Any:
        spec = get_spec(cls)
        if spec is not None:
            self.validate_one(path, spec.validator, data)
        return data

    def any(self, data: Any, path: Path) -> Any:
        return data

    def model(self, cls: Type[Model], data: Any, path: Path) -> Any:
        tmp = self.visit(get_model(cls), data, path)
        try:
            res = cls.from_model(tmp)
        except Exception as err:
            raise self.report(path, str(err))
        # noinspection PyUnboundLocalVariable
        self.validate(path, validators(cls), res)
        return res

    def optional(self, value: Type, data: Any, path: Path) -> Any:
        return None if data is None else self.visit(value, data, path)

    def union(self, alternatives: Iterable[Type], data: Any,
              path: Path) -> Any:
        alt_errors: List[Errors] = []
        for i, cls in enumerate(alternatives):
            nested_path = *path, UNION_PATH.format(index=i, cls=type_name(cls))
            with self.tmp_errors() as errors:
                try:
                    return self.visit(cls, data, nested_path)
                except ValidationError:
                    alt_errors.append(errors)
        self.merge(*alt_errors)
        raise ValidationError(self)

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 data: Any, path: Path) -> Any:
        self.check_type(path, data, list)
        elts: List[value_type] = []  # type: ignore
        nested_error = False
        for i, elt in enumerate(data):
            nested_path = *path, str(i)
            try:
                elts.append(self.visit(value_type, elt, nested_path))
            except ValidationError:
                nested_error = True
        if nested_error:
            raise ValidationError(self)
        # noinspection PyArgumentList
        return cls(elts)  # type: ignore

    def mapping(self, key_type: Type, value_type: Type, data: Any,
                path: Path) -> Any:
        self.check_type(path, data, dict)
        mapping: Dict[key_type, value_type] = {}  # type: ignore
        nested_error = False
        for key, value in data.items():
            assert isinstance(key, str)
            nested_path = *path, key
            try:
                new_key = self.visit(key_type, key, nested_path)
                mapping[new_key] = self.visit(value_type, value, nested_path)
            except ValidationError:
                nested_error = True
        if nested_error:
            raise ValidationError(self)
        return mapping

    def primitive(self, cls: Type, data: Any, path: Path) -> Any:
        self.check_type(path, data, cls)
        return data

    def dataclass(self, cls: Type[Cls], data: Any, path: Path) -> Any:
        assert is_dataclass(cls)
        self.check_type(path, data, dict)
        obj: Dict[str, Any] = {}
        nulls = []
        nested_error = False
        if not is_resolved(cls):
            resolve_types(cls)
        # noinspection PyDataclass
        for field in fields(cls):
            alias = camelize(get_aliased(field), self.camel_case)
            nested_path = *path, alias
            try:
                if alias in data:
                    if data[alias] is None:
                        nulls.append(field.name)
                    obj[field.name] = self.visit(field.type, data[alias],
                                                 nested_path)
                    if data[alias] is None or \
                            not hasattr(field, self.spec_key):
                        continue
                    spec = getattr(field, self.spec_key)
                    assert isinstance(spec, Spec)
                    self.validate_one(nested_path, spec.validator, data[alias])
                else:
                    try:
                        obj[field.name] = get_default(field)
                    except NoDefault:
                        raise self.report(
                            nested_path,
                            MISSING_FIELD.format(field=alias)
                        )
            except ValidationError:
                nested_error = True
        partials = validators(cls, PartialValidator)
        can_be_called = [pv for pv in partials if pv.can_be_called(obj)]
        if can_be_called:
            mock = set_null_values(ValidatorMock(obj, cls), *nulls)
            self.validate(path, can_be_called, mock)
        if nested_error:
            raise ValidationError(self)
        res = set_null_values(cls(**obj), *nulls)  # type: ignore
        self.validate(path, validators(cls), res)
        return res

    def enum(self, cls: Type[Enum], data: Any, path: Path) -> Any:
        try:
            # no need of validators for enum, same as primitive types
            # noinspection PyArgumentList
            return cls(data)
        except ValueError as err:
            raise self.report(path, str(err))

    def literal(self, values: Sequence[Any], data: Any, path: Path) -> Any:
        if data in values:
            return data
        else:
            raise self.report(path, WRONG_LITERAL.format(value=data,
                                                         values=values))


Cls = TypeVar("Cls")


def from_data(cls: Type[Cls], data: Any, camel_case=True,
              spec_key="spec") -> Cls:
    return FromData(camel_case, spec_key).visit(cls, data, ())


class ToData(Visitor[Any, Any]):
    def __init__(self, camel_case=True):
        super().__init__()
        self.camel_case = camel_case

    @staticmethod
    def check_type(obj: Any, expected: Type):
        if not isinstance(obj, expected):
            raise ValueError(WRONG_TYPE.format(expected=expected.__name__,
                                               type=type(obj).__name__))

    def any(self, obj: Any, path: Path) -> Any:
        return obj

    def model(self, cls: Type[Model], obj: Model, path: Path) -> Any:
        tmp = cls.to_model(obj)
        return self.visit(get_model(cls), tmp, path)

    def optional(self, value: Type, obj: Optional[Any], path: Path) -> Any:
        return None if obj is None else self.visit(value, obj, path)

    def union(self, alternatives: Iterable[Type], obj: Any, path: Path) -> Any:
        for i, cls in enumerate(alternatives):
            try:
                path = *path, UNION_PATH.format(index=i, cls=type_name(cls))
                return self.visit(cls, obj, path)
            except:  # noqa
                pass
        raise NotImplementedError()

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 obj: Iterable, path: Path) -> Any:
        self.check_type(obj, Iterable)
        return [self.visit(value_type, elt, (*path, str(i)))
                for i, elt in enumerate(obj)]

    def mapping(self, key_type: Type, value_type: Type,
                obj: Mapping, path: Path) -> Any:
        self.check_type(obj, dict)
        res: Dict[str, Any] = {}
        for key, value in obj.items():
            # cannot append key to path cause because it's not a string
            key = self.visit(key_type, key, path)
            res[key] = self.visit(value_type, value, (*path, key))
        return res

    def primitive(self, cls: Primitive, obj: Any, path: Path) -> Any:
        self.check_type(obj, cls)
        return obj

    def dataclass(self, cls: Type, obj: Any, path: Path) -> Any:
        type_hints = get_type_hints(cls)
        res: Dict[str, Any] = {}
        for field in fields(obj):
            value = getattr(obj, field.name)
            if value is None and field.name not in null_values(obj):
                continue
            alias = camelize(get_aliased(field), self.camel_case)
            res[alias] = self.visit(type_hints[field.name], value,
                                    (*path, alias))
        return res

    def enum(self, cls: Type[Enum], obj: Enum, path: Path) -> Any:
        self.check_type(obj, cls)
        return obj.value

    def literal(self, values: Sequence[Any], obj: Any, path: Path) -> Any:
        if obj not in values:
            raise ValueError(WRONG_LITERAL.format(value=obj, values=values))
        return obj


def to_data(cls: Type[Cls], obj: Cls, camel_case: bool = True) -> Any:
    return ToData(camel_case).visit(cls, obj, ())
