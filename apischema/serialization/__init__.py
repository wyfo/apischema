from enum import Enum
from functools import lru_cache, wraps
from operator import attrgetter
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
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.utils import Converter
from apischema.conversions.visitor import (
    RecursiveConversionsVisitor,
    Serialization,
    SerializationVisitor,
    sub_conversion,
)
from apischema.fields import FIELDS_SET_ATTR, fields_set, support_fields_set
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import SerializationObjectVisitor
from apischema.serialization.pass_through import PassThroughOptions, pass_through
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.types import AnyType, NoneType, Undefined
from apischema.typing import is_new_type, is_type, is_type_var, is_typed_dict
from apischema.utils import (
    Lazy,
    context_setter,
    deprecate_kwargs,
    get_origin_or_type,
    get_origin_or_type2,
    identity,
    opt_or,
)
from apischema.visitor import Unsupported

NEITHER_NONE_NOR_UNDEFINED = object()
NOT_NONE = object()


SerializationMethod = Callable[[Any], Any]
SerializationMethodFactory = Callable[[AnyType], SerializationMethod]


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
    RecursiveConversionsVisitor[Serialization, SerializationMethod],
    SerializationVisitor[SerializationMethod],
    SerializationObjectVisitor[SerializationMethod],
):
    def __init__(
        self,
        additional_properties: bool,
        aliaser: Aliaser,
        check_type: bool,
        default_conversion: DefaultConversion,
        exclude_unset: bool,
        fall_back_on_any: bool,
        pass_through_options: PassThroughOptions,
    ):
        super().__init__(default_conversion)
        self.additional_properties = additional_properties
        self.aliaser = aliaser
        self.pass_through_options = pass_through_options
        self._fall_back_on_any = fall_back_on_any
        self._check_type = check_type
        self._exclude_unset = exclude_unset

    def _recursive_result(self, lazy: Lazy[SerializationMethod]) -> SerializationMethod:
        rec_method = None

        def method(obj: Any) -> Any:
            nonlocal rec_method
            if rec_method is None:
                rec_method = lazy()
            return rec_method(obj)

        return method

    def pass_through(self, tp: AnyType) -> bool:
        try:
            return pass_through(
                tp,
                additional_properties=self.additional_properties,
                aliaser=self.aliaser,
                conversions=self._conversions,
                default_conversion=self.default_conversion,
                exclude_unset=self._exclude_unset,
                options=self.pass_through_options,
            )
        except (TypeError, Unsupported):  # TypeError because tp can be unhashable
            return False

    @property
    def _factory(self) -> SerializationMethodFactory:
        return serialization_method_factory(
            self.additional_properties,
            self.aliaser,
            self._check_type,
            self._conversions,
            self.default_conversion,
            self._exclude_unset,
            self._fall_back_on_any,
            self.pass_through_options,
        )

    def any(self) -> SerializationMethod:
        factory = self._factory

        def method(obj: Any) -> Any:
            return factory(obj.__class__)(obj)

        return method

    def _wrap(self, cls: type, method: SerializationMethod) -> SerializationMethod:
        if not self._check_type:
            return method
        fall_back_on_any, any_method = self._fall_back_on_any, self.any()
        if is_typed_dict(cls):
            cls = Mapping

        @wraps(method)
        def wrapper(obj: Any) -> Any:
            if isinstance(obj, cls):
                return method(obj)
            elif fall_back_on_any:
                return any_method(obj)
            else:
                raise TypeError(f"Expected {cls}, found {obj.__class__}")

        return wrapper

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> SerializationMethod:
        serialize_value = self.visit(value_type)

        # tuple would be slightly faster, but it's less intuitive to use it here
        if serialize_value is identity:
            method: SerializationMethod = list
        else:

            def method(obj: Any) -> Any:
                # using map is faster than comprehension
                return list(map(serialize_value, obj))

        return self._wrap(cls, method)

    def enum(self, cls: Type[Enum]) -> SerializationMethod:
        any_method = self.any()

        if self.pass_through_options.any or all(
            self.pass_through(elt.value.__class__) for elt in cls
        ):
            method: SerializationMethod = attrgetter("value")
        else:

            def method(obj: Any) -> Any:
                return any_method(obj.value)

        return self._wrap(cls, method)

    def literal(self, values: Sequence[Any]) -> SerializationMethod:
        return self.any()

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> SerializationMethod:
        serialize_key, serialize_value = self.visit(key_type), self.visit(value_type)
        if serialize_key is serialize_value is identity:
            method: SerializationMethod = dict
        else:

            def method(obj: Any) -> Any:
                return {
                    serialize_key(key): serialize_value(value)
                    for key, value in obj.items()
                }

        return self._wrap(cls, method)

    def object(self, tp: AnyType, fields: Sequence[ObjectField]) -> SerializationMethod:
        cls = get_origin_or_type(tp)
        identity_fields, normal_fields, skipped_if_fields, aggregate_fields = (
            [],
            [],
            [],
            [],
        )
        for field in fields:
            serialize_field = self.visit_with_conv(field.type, field.serialization)
            alias = self.aliaser(field.alias)
            if field.is_aggregate:
                aggregate_fields.append((field.name, serialize_field, field.skip_if))
            elif field.skip_if is not None:
                skipped_if_fields.append(
                    (field.name, alias, serialize_field, field.skip_if)
                )
            elif serialize_field is identity:
                identity_fields.append((field.name, alias))
            else:
                normal_fields.append((field.name, alias, serialize_field))
        serialized_methods = [
            (
                self.aliaser(name),
                serialized.func,
                self.visit_with_conv(types["return"], serialized.conversion),
            )
            for name, (serialized, types) in get_serialized_methods(tp).items()
        ]
        # Preallocate keys, notably to keep their order
        make_result = dict.fromkeys(
            self.aliaser(f.alias) for f in fields if not f.is_aggregate
        ).copy
        method: Callable
        if not is_typed_dict(cls):

            def method(
                obj: Any,
                aggregate_fields=tuple(aggregate_fields),
                identity_fields=tuple(identity_fields),
                normal_fields=tuple(normal_fields),
                skipped_if_fields=tuple(skipped_if_fields),
                make_result=make_result,
            ) -> Any:
                result = make_result()
                # aggregate before normal fields to avoid overloading
                for name, field_method, skip_if in aggregate_fields:
                    attr = getattr(obj, name)
                    if skip_if is None or not skip_if(attr):
                        result.update(field_method(attr))
                for name, alias, field_method, skip_if in skipped_if_fields:
                    attr = getattr(obj, name)
                    if skip_if(attr):
                        result.pop(alias, ...)
                    else:
                        result[alias] = field_method(attr)
                for name, alias in identity_fields:
                    result[alias] = getattr(obj, name)
                for name, alias, field_method in normal_fields:
                    result[alias] = field_method(getattr(obj, name))
                return result

            if self._exclude_unset and support_fields_set(cls):
                wrapped_exclude_unset = method

                def method(obj: Any) -> Any:
                    if hasattr(obj, FIELDS_SET_ATTR):
                        fields_set_ = fields_set(obj)
                        new_fields = [
                            [(name, *_) for name, *_ in fields if name in fields_set_]  # type: ignore
                            for fields in [
                                aggregate_fields,
                                identity_fields,
                                normal_fields,
                                skipped_if_fields,
                            ]
                        ]
                        return wrapped_exclude_unset(obj, *new_fields, lambda: {})
                    return wrapped_exclude_unset(obj)

        else:

            def method(obj: Mapping) -> dict:
                result = make_result()
                # aggregate before normal fields to avoid overloading
                for name, field_method, skip_if in aggregate_fields:
                    if name in obj and (skip_if is None or not skip_if(obj[name])):
                        result.update(field_method(obj[name]))
                for name, alias, field_method, skip_if in skipped_if_fields:
                    if name in obj and not skip_if(obj[name]):
                        result[alias] = field_method(obj[name])
                    else:
                        del result[alias]
                for name, alias in identity_fields:
                    if name in obj:
                        result[alias] = obj[name]
                    else:
                        del result[alias]
                for name, alias, field_method in normal_fields:
                    if name in obj:
                        result[alias] = field_method(obj[name])
                    else:
                        del result[alias]
                return result

            if self.additional_properties:
                wrapped_additional = method
                field_names = {f.name for f in fields if not f.is_aggregate}
                any_method = self.any()

                def method(obj: Mapping) -> Mapping:
                    result = wrapped_additional(obj)
                    for key, value in obj.items():
                        if key not in field_names:
                            result[key] = any_method(value)
                    return result

        if serialized_methods:
            wrapped_serialized = method

            def method(obj: Any) -> Any:
                result = wrapped_serialized(obj)
                for alias, func, serialized_method in serialized_methods:
                    res = func(obj)
                    if res is not Undefined:
                        result[alias] = serialized_method(res)
                return result

        return self._wrap(cls, method)

    def primitive(self, cls: Type) -> SerializationMethod:
        return self._wrap(cls, identity)

    def tuple(self, types: Sequence[AnyType]) -> SerializationMethod:
        elt_serializers = list(map(self.visit, types))

        def method(obj: Any) -> Any:
            return [
                serialize_elt(elt) for serialize_elt, elt in zip(elt_serializers, obj)
            ]

        if self._check_type:
            wrapped = method
            fall_back_on_any, as_list = self._fall_back_on_any, self._factory(list)

            def method(obj: Any) -> Any:
                if len(obj) == len(elt_serializers):
                    return wrapped(obj)
                elif fall_back_on_any:
                    return as_list(obj)
                else:
                    raise TypeError(
                        f"Expected {len(elt_serializers)}-tuple,"
                        f" found {len(obj)}-tuple"
                    )

        return self._wrap(tuple, method)

    def union(self, alternatives: Sequence[AnyType]) -> SerializationMethod:
        methods = self._union_results(alternatives, skip={NoneType})
        checks = [instance_checker(alt) for alt in alternatives if alt is not NoneType]
        methods_and_checks = list(zip(methods, checks))
        none_check = None if NoneType in alternatives else NOT_NONE
        fall_back_on_any, any_method = self._fall_back_on_any, self.any()

        def method(obj: Any) -> Any:
            # Optional/Undefined optimization
            if obj is none_check:
                return obj
            error = None
            for alt_method, instance_check in methods_and_checks:
                if not instance_check(obj):
                    continue
                try:
                    return alt_method(obj)
                except Exception as err:
                    error = err
            if fall_back_on_any:
                try:
                    return any_method(obj)
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
            if self._fall_back_on_any and is_type(tp):
                any_method = self.any()
                if issubclass(tp, Mapping):

                    def method(obj: Any) -> Any:
                        return {
                            any_method(key): any_method(value)
                            for key, value in obj.items()
                        }

                    return method

                elif issubclass(tp, Collection):

                    def method(obj: Any) -> Any:
                        return list(map(any_method, obj))

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
        elif serialize_conv is identity:
            return converter
        else:

            def method(obj: Any) -> Any:
                return serialize_conv(converter(obj))

        return self._wrap(get_origin_or_type(tp), method)

    def visit(self, tp: AnyType) -> SerializationMethod:
        if tp is AliasedStr:
            return self._wrap(AliasedStr, self.aliaser)
        elif not self._check_type and self.pass_through(tp):
            return identity
        else:
            return super().visit(tp)


@cache
def serialization_method_factory(
    additional_properties: Optional[bool],
    aliaser: Optional[Aliaser],
    check_type: Optional[bool],
    conversion: Optional[AnyConversion],
    default_conversion: Optional[DefaultConversion],
    exclude_unset: Optional[bool],
    fall_back_on_any: Optional[bool],
    pass_through: Optional[PassThroughOptions],
) -> SerializationMethodFactory:
    @lru_cache(serialization_method_factory.cache_info().maxsize)  # type: ignore
    def factory(tp: AnyType) -> SerializationMethod:
        from apischema import settings

        return SerializationMethodVisitor(
            opt_or(additional_properties, settings.additional_properties),
            opt_or(aliaser, settings.aliaser),
            opt_or(check_type, settings.serialization.check_type),
            opt_or(default_conversion, settings.serialization.default_conversion),
            opt_or(exclude_unset, settings.serialization.exclude_unset),
            opt_or(fall_back_on_any, settings.serialization.fall_back_on_any),
            opt_or(pass_through, settings.serialization.pass_through),
        ).visit_with_conv(tp, conversion)

    return factory


def serialization_method(
    type: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = None,
    pass_through: PassThroughOptions = None,
) -> SerializationMethod:
    return serialization_method_factory(
        additional_properties,
        aliaser,
        check_type,
        conversion,
        default_conversion,
        exclude_unset,
        fall_back_on_any,
        pass_through,
    )(type)


NO_OBJ = object()


@overload
def serialize(
    type: AnyType,
    obj: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = None,
    pass_through: PassThroughOptions = None,
) -> Any:
    ...


@overload
def serialize(
    obj: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = True,
    pass_through: PassThroughOptions = None,
) -> Any:
    ...


@deprecate_kwargs({"conversions": "conversion"})  # type: ignore
def serialize(
    type: AnyType = Any,
    obj: Any = NO_OBJ,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    check_type: bool = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = None,
    pass_through: PassThroughOptions = None,
) -> Any:
    # Handle overloaded signature without type
    if obj is NO_OBJ:
        type, obj = Any, type
        if fall_back_on_any is None:
            fall_back_on_any = True
    return serialization_method_factory(
        additional_properties,
        aliaser,
        check_type,
        conversion,
        default_conversion,
        exclude_unset,
        fall_back_on_any,
        pass_through,
    )(type)(obj)


def serialization_default(
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    default_conversion: DefaultConversion = None,
    exclude_unset: bool = None,
) -> SerializationMethod:
    factory = serialization_method_factory(
        additional_properties,
        aliaser,
        False,
        None,
        default_conversion,
        exclude_unset,
        False,
        # Annotations are lost in default fallback, so there will be `Any` everywhere;
        # passing through it allows optimizing containers
        PassThroughOptions(any=True),
    )

    def method(obj: Any) -> Any:
        return factory(obj.__class__)(obj)

    return method
