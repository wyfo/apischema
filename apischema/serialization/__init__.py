import collections.abc
import operator
from enum import Enum
from typing import (
    Any,
    Callable,
    Collection,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.utils import Converter
from apischema.conversions.visitor import (
    Serialization,
    SerializationVisitor,
    sub_conversion,
)
from apischema.fields import FIELDS_SET_ATTR, support_fields_set
from apischema.objects import AliasedStr, ObjectField
from apischema.objects.visitor import SerializationObjectVisitor
from apischema.recursion import RecursiveConversionsVisitor
from apischema.serialization.pass_through import PassThroughOptions, pass_through
from apischema.serialization.serialized_methods import get_serialized_methods
from apischema.types import AnyType, NoneType, Undefined, UndefinedType
from apischema.typing import is_new_type, is_type, is_type_var, is_typed_dict
from apischema.utils import (
    Lazy,
    deprecate_kwargs,
    get_origin_or_type,
    get_origin_or_type2,
    identity,
    is_union_of,
    opt_or,
)
from apischema.visitor import Unsupported

SerializationMethod = Callable[[Any], Any]
SerializationMethodFactory = Callable[[AnyType], SerializationMethod]


T = TypeVar("T")


def instance_checker(tp: AnyType) -> Tuple[Callable[[Any, Any], bool], Any]:
    tp = get_origin_or_type2(tp)
    if tp is NoneType:
        return operator.is_, None
    elif is_typed_dict(tp):
        return isinstance, collections.abc.Mapping
    elif is_type(tp):
        return isinstance, tp
    elif is_new_type(tp):
        return instance_checker(tp.__supertype__)
    elif is_type_var(tp) or tp is Any:
        return isinstance, object
    else:
        raise TypeError(f"{tp} is not supported in union serialization")


def identity_as_none(method: SerializationMethod) -> Optional[SerializationMethod]:
    return method if method is not identity else None


class SerializationMethodVisitor(
    RecursiveConversionsVisitor[Serialization, SerializationMethod],
    SerializationVisitor[SerializationMethod],
    SerializationObjectVisitor[SerializationMethod],
):
    use_cache: bool = True

    def __init__(
        self,
        additional_properties: bool,
        aliaser: Aliaser,
        check_type: bool,
        default_conversion: DefaultConversion,
        exclude_defaults: bool,
        exclude_none: bool,
        exclude_unset: bool,
        fall_back_on_any: bool,
        pass_through_options: PassThroughOptions,
    ):
        super().__init__(default_conversion)
        self.additional_properties = additional_properties
        self.aliaser = aliaser
        self.check_type = check_type
        self.exclude_defaults = exclude_defaults
        self.exclude_none = exclude_none
        self.exclude_unset = exclude_unset
        self.fall_back_on_any = fall_back_on_any
        self.pass_through_options = pass_through_options
        self._first_visit = True

    @property
    def _factory(self) -> SerializationMethodFactory:
        return serialization_method_factory(
            self.additional_properties,
            self.aliaser,
            self.check_type,
            self._conversion,
            self.default_conversion,
            self.exclude_defaults,
            self.exclude_none,
            self.exclude_unset,
            self.fall_back_on_any,
            self.pass_through_options,
        )

    def visit_not_recursive(self, tp: AnyType):
        if self._first_visit or not self.use_cache:
            self._first_visit = False
            return super().visit_not_recursive(tp)
        return self._factory(tp)

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
                conversions=self._conversion,
                default_conversion=self.default_conversion,
                exclude_defaults=self.exclude_defaults,
                exclude_none=self.exclude_none,
                exclude_unset=self.exclude_unset,
                options=self.pass_through_options,
            )
        except (TypeError, Unsupported):  # TypeError because tp can be unhashable
            return False

    def any(self) -> SerializationMethod:
        if self.pass_through_options.any:
            return identity
        factory = self._factory

        def method(obj: Any) -> Any:
            return factory(obj.__class__)(obj)

        return method

    def _any_fallback(self, tp: AnyType) -> SerializationMethod:
        serialize_any = self.any()

        def method(obj: Any) -> Any:
            if self.fall_back_on_any:
                return serialize_any(obj)
            else:
                raise TypeError(f"Expected {tp}, found {obj.__class__}")

        return method

    def _wrap(self, cls: type, method: SerializationMethod) -> SerializationMethod:
        if not self.check_type:
            return method
        fallback = self._any_fallback(cls)
        cls_to_check = Mapping if is_typed_dict(cls) else cls

        def wrapper(obj: Any) -> Any:
            if isinstance(obj, cls_to_check):
                try:
                    return method(obj)
                except Exception:
                    return fallback(obj)
            else:
                return fallback(obj)

        return wrapper

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> SerializationMethod:
        serialize_value = self.visit(value_type)

        if serialize_value is identity:
            method: SerializationMethod = list
        else:

            def method(obj: Any) -> Any:
                # using map is faster than comprehension
                return list(map(serialize_value, obj))

        return self._wrap(cls, method)

    def enum(self, cls: Type[Enum]) -> SerializationMethod:
        pass_through = all(self.pass_through(elt.value.__class__) for elt in cls)
        serialize_value = identity if pass_through else self.any()
        if serialize_value is identity:
            method: SerializationMethod = operator.attrgetter("value")
        else:

            def method(obj: Any) -> Any:
                return serialize_value(obj.value)

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
        typed_dict = is_typed_dict(cls)
        getter: Callable[[str], Callable[[Any], Any]] = (
            operator.itemgetter if typed_dict else operator.attrgetter
        )
        serialization_fields = [
            (
                cast(Optional[str], field.name),
                self.aliaser(field.alias) if not field.is_aggregate else None,
                getter(field.name),
                field.required,
                field.skip.serialization_if,
                is_union_of(field.type, UndefinedType) or default is Undefined,
                (is_union_of(field.type, NoneType) and self.exclude_none)
                or field.none_as_undefined
                or (default is None and self.exclude_defaults),
                (field.skip.serialization_default or self.exclude_defaults)
                and default not in (None, Undefined),
                default,
                identity_as_none(self.visit_with_conv(field.type, field.serialization)),
            )
            for field in fields
            for default in [... if field.required else field.get_default()]
        ] + [
            (
                None,
                self.aliaser(name),
                serialized.func,
                True,
                None,
                is_union_of(ret_type, UndefinedType),
                is_union_of(ret_type, NoneType) and self.exclude_none,
                False,
                ...,
                self.visit_with_conv(ret_type, serialized.conversion),
            )
            for name, (serialized, types) in get_serialized_methods(tp).items()
            for ret_type in [types["return"]]
        ]
        field_names = {f.name for f in fields}
        any_method = self.any()
        exclude_unset = self.exclude_unset and support_fields_set(cls)
        additional_properties = self.additional_properties and typed_dict

        def method(obj: Any) -> Any:
            result = {}
            for (
                name,
                alias,
                get_field,
                required,
                skip_if,
                undefined,
                skip_none,
                skip_default,
                default,
                serialize_field,
            ) in serialization_fields:
                if (exclude_unset and name not in getattr(obj, FIELDS_SET_ATTR)) or (
                    typed_dict and not required and name not in obj
                ):
                    continue
                field_value = get_field(obj)
                if (
                    (skip_if and skip_if(field_value))
                    or (undefined and field_value is Undefined)
                    or (skip_none and field_value is None)
                    or (skip_default and field_value == default)
                ):
                    continue
                if serialize_field:
                    field_value = serialize_field(field_value)
                if alias:
                    result[alias] = field_value
                else:
                    result.update(field_value)
            if additional_properties:
                assert isinstance(obj, Mapping)
                for key, value in obj.items():
                    if key not in field_names and isinstance(key, str):
                        result[key] = any_method(value)
            return result

        return self._wrap(cls, method)

    def primitive(self, cls: Type) -> SerializationMethod:
        return self._wrap(cls, identity)

    def tuple(self, types: Sequence[AnyType]) -> SerializationMethod:
        elt_serializers = list(enumerate(map(self.visit, types)))
        nb_elts = len(elt_serializers)

        def method(obj: Any) -> Any:
            return [serialize_elt(obj[i]) for i, serialize_elt in elt_serializers]

        if self.check_type:
            wrapped = method
            fall_back_on_any, as_list = self.fall_back_on_any, self._factory(list)

            def method(obj: Any) -> Any:
                if len(obj) == nb_elts:
                    return wrapped(obj)
                elif fall_back_on_any:
                    return as_list(obj)
                else:
                    raise TypeError(f"Expected {nb_elts}-tuple, found {len(obj)}-tuple")

        return self._wrap(tuple, method)

    def union(self, alternatives: Sequence[AnyType]) -> SerializationMethod:
        methods = self._union_results(alternatives)
        if len(methods) == 1:
            return methods[0]
        method_and_checks = [
            (serialize_alt, is_instance, cls)
            for serialize_alt, (is_instance, cls) in zip(
                methods, map(instance_checker, alternatives)
            )
        ]
        fallback = self._any_fallback(Union[alternatives])
        # No need to catch the case with all methods being identity,
        # because passthrough
        if alternatives[-1] is NoneType and len(method_and_checks) == 2:
            serialize_alt, is_instance, cls = method_and_checks[0]

            def method(obj: Any) -> Any:
                if is_instance(obj, cls):
                    return serialize_alt(obj)
                elif obj is None:
                    return None
                else:
                    return fallback(obj)

        else:

            def method(obj: Any) -> Any:
                for serialize_alt, is_instance, cls in method_and_checks:
                    if is_instance(obj, cls):
                        try:
                            return serialize_alt(obj)
                        except Exception:
                            pass
                return fallback(obj)

        return method

    def unsupported(self, tp: AnyType) -> SerializationMethod:
        try:
            return super().unsupported(tp)
        except Unsupported:
            if self.fall_back_on_any and is_type(tp):
                if issubclass(tp, Mapping):
                    return self.visit(Mapping[Any, Any])
                elif issubclass(tp, Collection):
                    return self.visit(Collection[Any])
            raise

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Serialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> SerializationMethod:
        serialize_conv = self.visit_with_conv(
            conversion.target, sub_conversion(conversion, next_conversion)
        )
        converter = cast(Converter, conversion.converter)
        if converter is identity:
            method = serialize_conv
        elif serialize_conv is identity:
            method = converter
        else:

            def method(obj: Any) -> Any:
                return serialize_conv(converter(obj))

        return self._wrap(get_origin_or_type(tp), method)

    def visit(self, tp: AnyType) -> SerializationMethod:
        if tp is AliasedStr:
            return self._wrap(AliasedStr, self.aliaser)
        elif not self.check_type and self.pass_through(tp):
            return identity
        else:
            return super().visit(tp)


@cache
def serialization_method_factory(
    additional_properties: bool,
    aliaser: Aliaser,
    check_type: bool,
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
    exclude_defaults: bool,
    exclude_none: bool,
    exclude_unset: bool,
    fall_back_on_any: bool,
    pass_through: PassThroughOptions,
) -> SerializationMethodFactory:
    @cache
    def factory(tp: AnyType) -> SerializationMethod:
        return SerializationMethodVisitor(
            additional_properties,
            aliaser,
            check_type,
            default_conversion,
            exclude_defaults,
            exclude_none,
            exclude_unset,
            fall_back_on_any,
            pass_through,
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
    exclude_defaults: bool = None,
    exclude_none: bool = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = None,
    pass_through: PassThroughOptions = None,
) -> SerializationMethod:
    from apischema import settings

    return serialization_method_factory(
        opt_or(additional_properties, settings.additional_properties),
        opt_or(aliaser, settings.aliaser),
        opt_or(check_type, settings.serialization.check_type),
        conversion,
        opt_or(default_conversion, settings.serialization.default_conversion),
        opt_or(exclude_defaults, settings.serialization.exclude_defaults),
        opt_or(exclude_none, settings.serialization.exclude_none),
        opt_or(exclude_unset, settings.serialization.exclude_unset),
        opt_or(fall_back_on_any, settings.serialization.fall_back_on_any),
        opt_or(pass_through, settings.serialization.pass_through),
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
    exclude_defaults: bool = None,
    exclude_none: bool = None,
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
    exclude_defaults: bool = None,
    exclude_none: bool = None,
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
    exclude_defaults: bool = None,
    exclude_none: bool = None,
    exclude_unset: bool = None,
    fall_back_on_any: bool = None,
    pass_through: PassThroughOptions = None,
) -> Any:
    # Handle overloaded signature without type
    if obj is NO_OBJ:
        type, obj = Any, type
        if fall_back_on_any is None:
            fall_back_on_any = True
    return serialization_method(
        type,
        additional_properties=additional_properties,
        aliaser=aliaser,
        check_type=check_type,
        conversion=conversion,
        default_conversion=default_conversion,
        exclude_defaults=exclude_defaults,
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
        fall_back_on_any=fall_back_on_any,
        pass_through=pass_through,
    )(obj)


def serialization_default(
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    default_conversion: DefaultConversion = None,
    exclude_defaults: bool = None,
    exclude_none: bool = None,
    exclude_unset: bool = None,
) -> SerializationMethod:
    from apischema import settings

    factory = serialization_method_factory(
        opt_or(additional_properties, settings.additional_properties),
        opt_or(aliaser, settings.aliaser),
        False,
        None,
        opt_or(default_conversion, settings.serialization.default_conversion),
        opt_or(exclude_defaults, settings.serialization.exclude_defaults),
        opt_or(exclude_none, settings.serialization.exclude_none),
        opt_or(exclude_unset, settings.serialization.exclude_unset),
        False,
        PassThroughOptions(any=True),
    )

    def method(obj: Any) -> Any:
        return factory(obj.__class__)(obj)

    return method
