from dataclasses import dataclass, field
from typing import AbstractSet, Any, Callable, Dict, Optional, Tuple, Union

from apischema.conversions.utils import Converter
from apischema.fields import FIELDS_SET_ATTR
from apischema.serialization.errors import TypeCheckError
from apischema.types import AnyType, Undefined
from apischema.utils import Lazy


class SerializationMethod:
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        raise NotImplementedError


class IdentityMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return obj


class ListMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return list(obj)


class DictMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return dict(obj)


class StrMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return str(obj)


class IntMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return int(obj)


class BoolMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return bool(obj)


class FloatMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return float(obj)


class NoneMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return None


@dataclass
class RecMethod(SerializationMethod):
    lazy: Lazy[SerializationMethod]
    method: Optional[SerializationMethod] = field(init=False)

    def __post_init__(self):
        self.method = None

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        if self.method is None:
            self.method = self.lazy()
        return self.method.serialize(obj)


@dataclass
class AnyMethod(SerializationMethod):
    factory: Callable[[AnyType], SerializationMethod]

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        method = self.factory(obj.__class__)  # tmp  variable for substitution
        return method.serialize(obj, path)


class Fallback:
    def fall_back(self, obj: Any, path: Union[int, str, None]) -> Any:
        raise NotImplementedError


@dataclass
class NoFallback(Fallback):
    tp: AnyType

    def fall_back(self, obj: Any, path: Union[int, str, None]) -> Any:
        raise TypeCheckError(
            f"Expected {self.tp}, found {obj.__class__}",
            [path] if path is not None else [],
        )


@dataclass
class AnyFallback(Fallback):
    any_method: SerializationMethod

    def fall_back(self, obj: Any, key: Union[int, str, None]) -> Any:
        return self.any_method.serialize(obj, key)


@dataclass
class TypeCheckIdentityMethod(SerializationMethod):
    expected: AnyType  # `type` would require exact match (i.e. no EnumMeta)
    fallback: Fallback

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return (
            obj
            if isinstance(obj, self.expected)
            else self.fallback.fall_back(obj, path)
        )


@dataclass
class TypeCheckMethod(SerializationMethod):
    method: SerializationMethod
    expected: AnyType  # `type` would require exact match (i.e. no EnumMeta)
    fallback: Fallback

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        if isinstance(obj, self.expected):
            try:
                return self.method.serialize(obj)
            except TypeCheckError as err:
                if path is None:
                    raise
                raise TypeCheckError(err.msg, [path, *err.loc])
        else:
            return self.fallback.fall_back(obj, path)


@dataclass
class CollectionCheckOnlyMethod(SerializationMethod):
    value_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        for i, elt in enumerate(obj):
            self.value_method.serialize(elt, i)
        return obj


@dataclass
class CollectionMethod(SerializationMethod):
    value_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return [self.value_method.serialize(elt, i) for i, elt in enumerate(obj)]


class ValueMethod(SerializationMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return obj.value


@dataclass
class EnumMethod(SerializationMethod):
    any_method: AnyMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return self.any_method.serialize(obj.value)


@dataclass
class MappingCheckOnlyMethod(SerializationMethod):
    key_method: SerializationMethod
    value_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        for key, value in obj.items():
            self.key_method.serialize(key, key)
            self.value_method.serialize(value, key)
        return obj


@dataclass
class MappingMethod(SerializationMethod):
    key_method: SerializationMethod
    value_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return {
            self.key_method.serialize(key, key): self.value_method.serialize(value, key)
            for key, value in obj.items()
        }


class BaseField:
    def update_result(
        self, obj: Any, result: dict, typed_dict: bool, exclude_unset: bool
    ):
        raise NotImplementedError


@dataclass
class IdentityField(BaseField):
    name: str
    alias: str
    required: bool

    def update_result(
        self, obj: Any, result: dict, typed_dict: bool, exclude_unset: bool
    ):
        if serialize_field(self, obj, typed_dict, exclude_unset):
            result[self.alias] = get_field_value(self, obj, typed_dict)


def serialize_field(
    field: IdentityField, obj: Any, typed_dict: bool, exclude_unset: bool
) -> bool:
    if typed_dict:
        return field.required or field.name in obj
    else:
        return not exclude_unset or field.name in getattr(obj, FIELDS_SET_ATTR)


def get_field_value(field: IdentityField, obj: Any, typed_dict: bool) -> object:
    return obj[field.name] if typed_dict else getattr(obj, field.name)


@dataclass
class SimpleField(IdentityField):
    method: SerializationMethod

    def update_result(
        self, obj: Any, result: dict, typed_dict: bool, exclude_unset: bool
    ):
        if serialize_field(self, obj, typed_dict, exclude_unset):
            result[self.alias] = self.method.serialize(
                get_field_value(self, obj, typed_dict), self.alias
            )


@dataclass
class ComplexField(SimpleField):
    skip_if: Optional[Callable]
    undefined: bool
    skip_none: bool
    skip_default: bool
    default_value: Any  # https://github.com/cython/cython/issues/4383
    skippable: bool = field(init=False)

    def __post_init__(self):
        self.skippable = (
            self.skip_if or self.undefined or self.skip_none or self.skip_default
        )

    def update_result(
        self, obj: Any, result: dict, typed_dict: bool, exclude_unset: bool
    ):
        if serialize_field(self, obj, typed_dict, exclude_unset):
            value: object = get_field_value(self, obj, typed_dict)
            if not self.skippable or not (
                (self.skip_if is not None and self.skip_if(value))
                or (self.undefined and value is Undefined)
                or (self.skip_none and value is None)
                or (self.skip_default and value == self.default_value)
            ):
                if self.alias is not None:
                    result[self.alias] = self.method.serialize(value, self.alias)
                else:
                    result.update(self.method.serialize(value, self.alias))


@dataclass
class SerializedField(BaseField):
    alias: str
    func: Callable[[Any], Any]
    undefined: bool
    skip_none: bool
    method: SerializationMethod

    def update_result(
        self, obj: Any, result: dict, typed_dict: bool, exclude_unset: bool
    ):
        value = self.func(obj)
        if not (self.undefined and value is Undefined) and not (
            self.skip_none and value is None
        ):
            result[self.alias] = self.method.serialize(value, self.alias)


@dataclass
class ObjectMethod(SerializationMethod):
    fields: Tuple[BaseField, ...]


@dataclass
class ClassMethod(ObjectMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        result: dict = {}
        for i in range(len(self.fields)):
            field: BaseField = self.fields[i]
            field.update_result(obj, result, False, False)
        return result


@dataclass
class ClassWithFieldsSetMethod(ObjectMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        result: dict = {}
        for i in range(len(self.fields)):
            field: BaseField = self.fields[i]
            field.update_result(obj, result, False, True)
        return result


@dataclass
class TypedDictMethod(ObjectMethod):
    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        result: dict = {}
        for i in range(len(self.fields)):
            field: BaseField = self.fields[i]
            field.update_result(obj, result, True, False)
        return result


@dataclass
class TypedDictWithAdditionalMethod(TypedDictMethod):
    field_names: AbstractSet[str]
    any_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        result: dict = super().serialize(obj)
        for key, value in obj.items():
            if key not in self.field_names and isinstance(key, str):
                result[str(key)] = self.any_method.serialize(value, key)
        return result


@dataclass
class TupleCheckOnlyMethod(SerializationMethod):
    elt_methods: Tuple[SerializationMethod, ...]

    def serialize(self, obj: tuple, path: Union[int, str, None] = None) -> Any:
        for i in range(len(self.elt_methods)):
            method: SerializationMethod = self.elt_methods[i]
            method.serialize(obj[i], i)
        return obj


@dataclass
class TupleMethod(SerializationMethod):
    elt_methods: Tuple[SerializationMethod, ...]

    def serialize(self, obj: tuple, path: Union[int, str, None] = None) -> Any:
        elts: list = [None] * len(self.elt_methods)
        for i in range(len(self.elt_methods)):
            method: SerializationMethod = self.elt_methods[i]
            elts[i] = method.serialize(obj[i], i)
        return elts


@dataclass
class CheckedTupleMethod(SerializationMethod):
    nb_elts: int
    method: SerializationMethod

    def serialize(self, obj: tuple, path: Union[int, str, None] = None) -> Any:
        if not len(obj) == self.nb_elts:
            raise TypeError(f"Expected {self.nb_elts}-tuple, found {len(obj)}-tuple")
        return self.method.serialize(obj)


# There is no need of an OptionalIdentityMethod because it would mean that all methods
# are IdentityMethod, which gives IdentityMethod.


@dataclass
class OptionalMethod(SerializationMethod):
    value_method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return self.value_method.serialize(obj, path) if obj is not None else None


@dataclass
class UnionAlternative(SerializationMethod):
    cls: AnyType  # `type` would require exact match (i.e. no EnumMeta)
    method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return self.method.serialize(obj, path)


@dataclass
class DiscriminatedAlternative(UnionAlternative):
    alias: str
    key: str

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        res = super().serialize(obj, path)
        if isinstance(res, dict) and self.alias not in res:
            res[self.alias] = self.key
        return res


@dataclass
class UnionMethod(SerializationMethod):
    alternatives: Tuple[UnionAlternative, ...]
    fallback: Fallback

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        for i in range(len(self.alternatives)):
            alternative: UnionAlternative = self.alternatives[i]
            if isinstance(obj, alternative.cls):
                try:
                    return alternative.serialize(obj, path)
                except Exception:
                    pass
        return self.fallback.fall_back(obj, path)


@dataclass
class WrapperMethod(SerializationMethod):
    wrapped: Callable[[Any], Any]

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return self.wrapped(obj)


@dataclass
class ConversionMethod(SerializationMethod):
    converter: Converter
    method: SerializationMethod

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        return self.method.serialize(self.converter(obj))


@dataclass
class DiscriminateTypedDict(SerializationMethod):
    field_name: str
    mapping: Dict[str, SerializationMethod]
    fallback: Fallback

    def serialize(self, obj: Any, path: Union[int, str, None] = None) -> Any:
        try:
            method: SerializationMethod = self.mapping[obj[self.field_name]]
        except Exception:
            return self.fallback.fall_back(obj, path)
        return method.serialize(obj, path)
