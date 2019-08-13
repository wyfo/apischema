from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import (Any, Dict, Iterable, List, Optional,
                    Sequence, Tuple, Type, TypeVar, get_type_hints)

import humps
from tmv import Primitive, type_name

from apischema.errors import (MISSING_FIELD, UNION_PATH, WRONG_LITERAL,
                              WRONG_TYPE)
from apischema.field import NoDefault, get_aliased, get_default
from apischema.model import Model, get_model
from apischema.null import null_values, set_null_values
from apischema.spec import Spec, get_spec
from apischema.types import is_resolved, resolve_types
from apischema.validation import Errors, Validation, ValidationError
from apischema.validator import (PartialValidator, Path, ValidatorMock,
                                 validators)
from apischema.visitor import Aliaser, Visitor, camel_case_aliaser

Context = Tuple[Any, Path]


# noinspection PyAbstractClass
class FromData(Visitor[Any, Context], Validation):
    def __init__(self, *, spec_key="spec",
                 aliaser: Optional[Aliaser]):
        Visitor.__init__(self, aliaser)
        Validation.__init__(self)
        self.spec_key = spec_key

    def check_class(self, cls: Type, data: Any, path: Path) -> Any:
        spec = get_spec(cls)
        if spec is not None:
            self.validate_one(path, spec.validator, data)

    def primitive(self, cls: Primitive, ctx: Context) -> Any:
        data, path = ctx
        self.check_type(path, data, cls)
        return data

    def optional(self, value: Type, ctx: Context) -> Any:
        data, path = ctx
        return None if data is None else self.visit(value, ctx)

    def union(self, alternatives: Iterable[Type], ctx: Context) -> Any:
        data, path = ctx
        alt_errors: List[Errors] = []
        for i, cls in enumerate(alternatives):
            nested_path = *path, UNION_PATH.format(index=i, cls=type_name(cls))
            with self.tmp_errors() as errors:
                try:
                    return self.visit(cls, (data, nested_path))
                except ValidationError:
                    alt_errors.append(errors)
        self.merge(*alt_errors)
        raise ValidationError(self)

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 ctx: Context) -> Any:
        data, path = ctx
        self.check_type(path, data, list)
        elts: List[value_type] = []  # type: ignore
        nested_error = False
        for i, elt in enumerate(data):
            nested_path = *path, str(i)
            try:
                elts.append(self.visit(value_type, (elt, nested_path)))
            except ValidationError:
                nested_error = True
        if nested_error:
            raise ValidationError(self)
        # noinspection PyArgumentList
        return cls(elts)  # type: ignore

    def mapping(self, key_type: Type, value_type: Type,
                ctx: Context) -> Any:
        data, path = ctx
        self.check_type(path, data, dict)
        mapping: Dict[key_type, value_type] = {}  # type: ignore
        nested_error = False
        for key, value in data.items():
            assert isinstance(key, str)
            nested_path = *path, key
            try:
                new_key = self.visit(key_type, (key, nested_path))
                mapping[new_key] = self.visit(value_type, (value, nested_path))
            except ValidationError:
                nested_error = True
        if nested_error:
            raise ValidationError(self)
        return mapping

    def literal(self, values: Sequence[Any], ctx: Context) -> Any:
        data, path = ctx
        if data in values:
            return data
        else:
            raise self.report(path,
                              WRONG_LITERAL.format(value=data, values=values))

    def custom(self, cls: Type[Model], ctx: Context) -> Any:
        data, path = ctx
        self.check_class(cls, data, path)
        tmp = self.visit(get_model(cls), ctx)
        try:
            res = cls.from_model(tmp)
        except Exception as err:
            raise self.report(path, str(err))
        # noinspection PyUnboundLocalVariable
        self.validate(path, validators(cls), res)
        return res

    def dataclass(self, cls: Type, ctx: Context) -> Any:
        assert is_dataclass(cls)
        data, path = ctx
        self.check_type(path, data, dict)
        self.check_class(cls, data, path)
        obj: Dict[str, Any] = {}
        nulls = []
        nested_error = False
        if not is_resolved(cls):
            resolve_types(cls)
        # noinspection PyDataclass
        for field in fields(cls):
            alias = self.aliaser(get_aliased(field))
            nested_path = *path, alias
            try:
                if alias in data:
                    if data[alias] is None:
                        nulls.append(field.name)
                    obj[field.name] = self.visit(field.type,
                                                 (data[alias], nested_path))
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

    def enum(self, cls: Type[Enum], ctx: Context) -> Any:
        data, path = ctx
        try:
            # no need of validators for enum, same as primitive types
            # noinspection PyArgumentList
            return cls(data)
        except ValueError as err:
            raise self.report(path, str(err))

    def any(self, ctx: Context) -> Any:
        data, path = ctx
        return data


Cls = TypeVar("Cls")


def from_data(cls: Type[Cls], data: Any, camel_case=True) -> Cls:
    aliaser = camel_case_aliaser(camel_case)
    return FromData(aliaser=aliaser).visit(cls, (data, ()))


# noinspection PyAbstractClass
class ToData(Visitor[Any, Any]):
    def __init__(self, aliaser: Optional[Aliaser] = humps.camelize):
        super().__init__(aliaser)
        self.aliaser = aliaser or (lambda s: s)

    @staticmethod
    def check_type(obj: Any, expected: Type):
        if not isinstance(obj, expected):
            raise ValueError(WRONG_TYPE.format(expected=expected.__name__,
                                               type=type(obj).__name__))

    def primitive(self, cls: Primitive, obj: Any) -> Any:
        self.check_type(obj, cls)
        return obj

    def optional(self, value: Type, obj: Any) -> Any:
        return None if obj is None else self.visit(value, obj)

    def union(self, alternatives: Iterable[Type], obj: Any) -> Any:
        for cls in alternatives:
            try:
                return self.visit(cls, obj)
            except:  # noqa
                pass
        # TODO Better error handling
        raise ValueError()

    def iterable(self, cls: Type[Iterable], value_type: Type,
                 obj: Any) -> Any:
        self.check_type(obj, Iterable)
        return [self.visit(value_type, elt) for elt in obj]

    def mapping(self, key_type: Type, value_type: Type,
                obj: Any) -> Any:
        self.check_type(obj, dict)
        return {self.visit(key_type, key): self.visit(value_type, value)
                for key, value in obj.items()}

    def literal(self, values: Sequence[Any], obj: Any) -> Any:
        if obj not in values:
            raise ValueError(WRONG_LITERAL.format(value=obj, values=values))
        return obj

    def custom(self, cls: Type[Model], obj: Any) -> Any:
        tmp = cls.to_model(obj)
        return self.visit(get_model(cls), tmp)

    def dataclass(self, cls: Type, obj: Any) -> Any:
        type_hints = get_type_hints(cls)
        res: Dict[str, Any] = {}
        for field in fields(obj):
            value = getattr(obj, field.name)
            if value is None and field.name not in null_values(obj):
                continue
            alias = self.aliaser(get_aliased(field))
            res[alias] = self.visit(type_hints[field.name], value)
        return res

    def enum(self, cls: Type[Enum], obj: Any) -> Any:
        self.check_type(obj, cls)
        return obj.value

    def any(self, obj: Any) -> Any:
        return obj


def to_data(cls: Type[Cls], obj: Cls, camel_case: bool = True) -> Any:
    aliaser = camel_case_aliaser(camel_case)
    return ToData(aliaser=aliaser).visit(cls, obj)
