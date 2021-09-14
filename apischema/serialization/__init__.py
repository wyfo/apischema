from enum import Enum
from functools import lru_cache, wraps
from typing import (
    Any,
    Callable,
    Collection,
    Mapping,
    Optional,
    Sequence,
    Type,
    Union,
    cast,
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions import identity
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.utils import Converter
from apischema.conversions.visitor import (
    CachedConversionsVisitor,
    Serialization,
    SerializationVisitor,
    sub_conversion,
)
from apischema.fields import FIELDS_SET_ATTR, fields_set
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import SerializationObjectVisitor
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.types import AnyType, NoneType, Undefined, UndefinedType
from apischema.typing import is_new_type, is_type_var, is_typed_dict
from apischema.utils import (
    Lazy,
    context_setter,
    deprecate_kwargs,
    get_origin_or_type,
    get_origin_or_type2,
    opt_or,
)
from apischema.visitor import Unsupported

NEITHER_NONE_NOR_UNDEFINED = object()
NOT_NONE = object()


SerializationMethod = Callable[[Any], Any]


def instance_checker(tp: AnyType) -> Callable[[Any], bool]:
    tp = get_origin_or_type2(tp)
    if isinstance(tp, type):
        return lambda obj: isinstance(obj, tp)
    elif is_new_type(tp):
        return instance_checker(tp.__supertype__)
    elif is_type_var(tp):
        return lambda obj: True
    else:
        raise TypeError(f"{tp} is not supported in union serialization")


class SerializationMethodVisitor(
    CachedConversionsVisitor,
    SerializationVisitor[SerializationMethod],
    SerializationObjectVisitor[SerializationMethod],
):
    def __init__(
        self,
        aliaser: Aliaser,
        fall_back_on_any: bool,
        check_type: bool,
        default_conversion: DefaultConversion,
        exclude_unset: bool,
        allow_undefined: bool,
    ):
        super().__init__(default_conversion)
        self.aliaser = aliaser
        self._fall_back_on_any = fall_back_on_any
        self._check_type = check_type
        self._exclude_unset = exclude_unset
        self._allow_undefined = allow_undefined

    def _cache_result(self, lazy: Lazy[SerializationMethod]) -> SerializationMethod:
        rec_method = None

        def method(obj: Any) -> Any:
            nonlocal rec_method
            if rec_method is None:
                rec_method = lazy()
            return rec_method(obj)

        return method

    @property
    def _any_method(self) -> Callable[[type], SerializationMethod]:
        return serialization_method_factory(
            self.aliaser,
            self._fall_back_on_any,
            self._check_type,
            self._conversions,
            self.default_conversion,
            self._exclude_unset,
            allow_undefined=self._allow_undefined,
        )

    def _wrap_type_check(
        self, cls: type, method: SerializationMethod
    ) -> SerializationMethod:
        if not self._check_type:
            return method
        fall_back_on_any, any_method = self._fall_back_on_any, self._any_method

        @wraps(method)
        def wrapper(obj: Any) -> Any:
            if isinstance(obj, cls):
                return method(obj)
            elif fall_back_on_any:
                return any_method(obj.__class__)(obj)
            else:
                raise TypeError(f"Expected {cls}, found {obj.__class__}")

        return wrapper

    def any(self) -> SerializationMethod:
        any_method = self._any_method

        def method(obj: Any) -> Any:
            return any_method(obj.__class__)(obj)

        return method

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> SerializationMethod:
        serialize_value = self.visit(value_type)

        def method(obj: Any) -> Any:
            return [serialize_value(elt) for elt in obj]

        return self._wrap_type_check(cls, method)

    def enum(self, cls: Type[Enum]) -> SerializationMethod:
        any_method = self._any_method

        def method(obj: Any) -> Any:
            return any_method(obj.value.__class__)(obj.value)

        return self._wrap_type_check(cls, method)

    def literal(self, values: Sequence[Any]) -> SerializationMethod:
        return self.any()

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> SerializationMethod:
        serialize_key, serialize_value = self.visit(key_type), self.visit(value_type)

        def method(obj: Any) -> Any:
            return {
                serialize_key(key): serialize_value(value) for key, value in obj.items()
            }

        return self._wrap_type_check(cls, method)

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> SerializationMethod:
        with context_setter(self) as setter:
            setter._allow_undefined = True
            normal_fields, aggregate_fields = [], []
            for field in fields:
                serialize_field = self.visit_with_conv(field.type, field.serialization)
                if field.is_aggregate:
                    aggregate_fields.append((field.name, serialize_field))
                else:
                    normal_fields.append(
                        (field.name, str(self.aliaser(field.alias)), serialize_field)
                    )
            serialized_methods = [
                (
                    self.aliaser(name),
                    method.func,
                    self.visit_with_conv(types["return"], method.conversion),
                )
                for name, (method, types) in get_serialized_methods(tp).items()
            ]
        exclude_unset = self._exclude_unset

        def method(
            obj: Any,
            attr_getter=getattr,
            normal_fields=normal_fields,
            aggregate_fields=aggregate_fields,
        ) -> Any:
            result = {}
            # aggregate before normal fields to avoid overloading
            for name, field_method in aggregate_fields:
                attr = attr_getter(obj, name)
                result.update(field_method(attr))
            for name, alias, field_method in normal_fields:
                attr = attr_getter(obj, name)
                if attr is not Undefined:
                    result[alias] = field_method(attr)
            for alias, func, method in serialized_methods:
                res = func(obj)
                if res is not Undefined:
                    result[alias] = method(res)
            return result

        cls = get_origin_or_type(tp)
        if is_typed_dict(cls):
            cls, exclude_unset = Mapping, False
            wrapped_attr_getter = method

            def method(
                obj: Any,
                attr_getter=getattr,
                normal_fields=normal_fields,
                aggregate_fields=aggregate_fields,
            ) -> Any:
                return wrapped_attr_getter(
                    obj, type(obj).__getitem__, normal_fields, aggregate_fields
                )

        if exclude_unset:
            wrapped_exclude_unset = method

            def method(
                obj: Any,
                attr_getter=getattr,
                normal_fields=normal_fields,
                aggregate_fields=aggregate_fields,
            ) -> Any:
                if hasattr(obj, FIELDS_SET_ATTR):
                    fields_set_ = fields_set(obj)
                    normal_fields = [
                        (name, alias, method)
                        for (name, alias, method) in normal_fields
                        if name in fields_set_
                    ]
                    aggregate_fields = [
                        (name, method)
                        for (name, method) in aggregate_fields
                        if name in fields_set_
                    ]
                return wrapped_exclude_unset(
                    obj, attr_getter, normal_fields, aggregate_fields
                )

        return self._wrap_type_check(cls, method)

    def primitive(self, cls: Type) -> SerializationMethod:
        def method(obj: Any) -> Any:
            return obj

        return self._wrap_type_check(cls, method)

    def tuple(self, types: Sequence[AnyType]) -> SerializationMethod:
        elt_deserializers = list(map(self.visit, types))

        def method(obj: Any) -> Any:
            return [
                serialize_elt(elt) for serialize_elt, elt in zip(elt_deserializers, obj)
            ]

        if self._check_type:
            wrapped = method
            fall_back_on_any, as_list = self._fall_back_on_any, self._any_method(list)

            def method(obj: Any) -> Any:
                if len(obj) == len(elt_deserializers):
                    return wrapped(obj)
                elif fall_back_on_any:
                    return as_list(obj)
                else:
                    raise TypeError(
                        f"Expected {len(elt_deserializers)}-tuple,"
                        f" found {len(obj)}-tuple"
                    )

        return self._wrap_type_check(tuple, method)

    def union(self, alternatives: Sequence[AnyType]) -> SerializationMethod:
        method_and_checks = [
            (self.visit(alt), instance_checker(alt))
            for alt in alternatives
            if alt not in (None, UndefinedType)
        ]
        none_check = None if NoneType in alternatives else NOT_NONE
        undefined_allowed = UndefinedType in alternatives and self._allow_undefined
        fall_back_on_any, any_method = self._fall_back_on_any, self._any_method

        def method(obj: Any) -> Any:
            # Optional/Undefined optimization
            if obj is none_check:
                return obj
            error = None
            for alt_method, instance_check in method_and_checks:
                if not instance_check(obj):
                    continue
                try:
                    return alt_method(obj)
                except Exception as err:
                    error = err
            if obj is Undefined and undefined_allowed:
                return obj
            if fall_back_on_any:
                try:
                    return any_method(obj.__class__)(obj)
                except Exception as err:
                    error = err
            raise error or TypeError(
                f"Expected {Union[alternatives]}, found {obj.__class__}"
            )

        return method

    def unsupported(self, tp: AnyType) -> SerializationMethod:
        try:
            return super().unsupported(tp)
        except Unsupported:
            if self._fall_back_on_any and isinstance(tp, type):
                any_method = self._any_method
                if issubclass(tp, Mapping):

                    def method(obj: Any) -> Any:
                        return {
                            any_method(key.__class__)(key): any_method(value.__class__)(
                                value
                            )
                            for key, value in obj.items()
                        }

                    return method

                elif issubclass(tp, Collection):

                    def method(obj: Any) -> Any:
                        return [any_method(elt.__class__)(elt) for elt in obj]

                    return method

            raise

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Serialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> SerializationMethod:
        with context_setter(self) as setter:
            if conversion.fall_back_on_any is not None:
                setter._fall_back_on_any = conversion.fall_back_on_any
            if conversion.exclude_unset is not None:
                setter._exclude_unset = conversion.exclude_unset
            serialize_conv = self.visit_with_conv(
                conversion.target, sub_conversion(conversion, next_conversion)
            )

        converter = cast(Converter, conversion.converter)
        if converter is identity:
            method = serialize_conv
        else:

            def method(obj: Any) -> Any:
                return serialize_conv(converter(obj))

        return self._wrap_type_check(get_origin_or_type(tp), method)

    def visit(self, tp: AnyType) -> SerializationMethod:
        if tp == AliasedStr:
            return self._wrap_type_check(AliasedStr, self.aliaser)
        return super().visit(tp)


@cache
def serialization_method_factory(
    aliaser: Optional[Aliaser],
    fall_back_on_any: Optional[bool],
    check_type: Optional[bool],
    conversion: Optional[AnyConversion],
    default_conversion: Optional[DefaultConversion],
    exclude_unset: Optional[bool],
    allow_undefined: bool = False,
) -> Callable[[AnyType], SerializationMethod]:
    @lru_cache(serialization_method_factory.cache_info().maxsize)  # type: ignore
    def factory(tp: AnyType) -> SerializationMethod:
        from apischema import settings

        return SerializationMethodVisitor(
            opt_or(aliaser, settings.aliaser),
            opt_or(fall_back_on_any, settings.serialization.fall_back_on_any),
            opt_or(check_type, settings.serialization.check_type),
            opt_or(default_conversion, settings.serialization.default_conversion),
            opt_or(exclude_unset, settings.serialization.exclude_unset),
            allow_undefined,
        ).visit_with_conv(tp, conversion)

    return factory


def serialization_method(
    type: AnyType,
    *,
    aliaser: Aliaser = None,
    fall_back_on_any: bool = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
) -> SerializationMethod:
    return serialization_method_factory(
        aliaser,
        fall_back_on_any,
        check_type,
        conversion,
        default_conversion,
        exclude_unset,
    )(type)


NO_OBJ = object()


@overload
def serialize(
    type: AnyType,
    obj: Any,
    *,
    aliaser: Aliaser = None,
    fall_back_on_any: bool = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
) -> Any:
    ...


@overload
def serialize(
    obj: Any,
    *,
    aliaser: Aliaser = None,
    fall_back_on_any: bool = True,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
) -> Any:
    ...


@deprecate_kwargs({"conversions": "conversion"})  # type: ignore
def serialize(
    type: AnyType = Any,
    obj: Any = NO_OBJ,
    *,
    aliaser: Aliaser = None,
    fall_back_on_any: bool = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
) -> Any:
    # Handle overloaded signature without type
    if obj is NO_OBJ:
        type, obj = Any, type
        if fall_back_on_any is None:
            fall_back_on_any = True
    return serialization_method_factory(
        aliaser=aliaser,
        fall_back_on_any=fall_back_on_any,
        check_type=check_type,
        conversion=conversion,
        default_conversion=default_conversion,
        exclude_unset=exclude_unset,
    )(type)(obj)
