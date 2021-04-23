from contextlib import contextmanager
from dataclasses import replace
from types import new_class
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.cache import cache
from apischema.conversions import LazyConversion
from apischema.conversions.conversions import (
    Conversion,
    Conversions,
    ResolvedConversion,
    ResolvedConversions,
    handle_identity_conversion,
    is_identity,
    resolve_conversions,
    update_generics,
)
from apischema.conversions.converters import _deserializers, _serializers
from apischema.conversions.dataclass_models import handle_dataclass_model
from apischema.conversions.utils import INVALID_CONVERSION_TYPES
from apischema.skip import filter_skipped
from apischema.types import AnyType, Undefined, UndefinedType
from apischema.typing import get_args
from apischema.utils import (
    OperationKind,
    PREFIX,
    get_origin_or_type,
    has_type_vars,
)
from apischema.visitor import Return, Unsupported, Visitor

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Deserialization = Sequence[ResolvedConversion]
Serialization = ResolvedConversion
Conv = TypeVar("Conv")

SELF_CONVERSION_ATTR = f"{PREFIX}self_conversion"


class ConversionsVisitor(Visitor[Return], Generic[Conv, Return]):
    operation: OperationKind
    _dynamic_conversion_resolver: Type["DynamicConversionResolver"]

    def __init__(self):
        super().__init__()
        self._conversions: ResolvedConversions = ()

    @staticmethod
    def _get_conversions(
        tp: AnyType, conversions: ResolvedConversions
    ) -> Union[Conv, None, UndefinedType]:
        raise NotImplementedError

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        raise NotImplementedError

    def _handle_container_sub_conversions(self, conversion: Conv) -> Conv:
        raise NotImplementedError

    @classmethod
    def get_conversions(
        cls, tp: AnyType, conversions: ResolvedConversions
    ) -> Tuple[Optional[Conv], bool]:
        conv, dynamic = None, False
        if conversions is not None:
            conv = cls._get_conversions(tp, conversions)
        if conv is not None:
            dynamic = True
        else:
            default = cls._default_conversions(get_origin_or_type(tp))
            if default:
                conv = cls._get_conversions(tp, resolve_conversions(default))
        return (conv if conv is not Undefined else None), dynamic

    def _apply_dynamic_conversions(self, tp: AnyType) -> Optional[AnyType]:
        if not self._conversions:
            return None
        else:
            return self._dynamic_conversion_resolver().visit_with_conversions(
                tp, self._conversions
            )

    def visit_conversion(self, tp: AnyType, conversion: Conv, dynamic: bool) -> Return:
        raise NotImplementedError

    def visit_not_conversion(self, tp: AnyType, dynamic: bool) -> Return:
        return super().visit(tp)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self._conversions
        self._conversions = resolve_conversions(conversions)
        try:
            yield
        finally:
            self._conversions = conversions_save

    def visit(self, tp: AnyType) -> Return:
        origin = get_origin_or_type(tp)
        if origin in INVALID_CONVERSION_TYPES or not isinstance(origin, type):
            return self.visit_not_conversion(tp, False)
        conversion, dynamic = self.get_conversions(tp, self._conversions)
        reuse_conversions = not dynamic and issubclass(origin, Collection)
        if conversion is not None:
            if reuse_conversions:
                conversion = self._handle_container_sub_conversions(conversion)
            return self.visit_conversion(tp, conversion, dynamic)
        elif reuse_conversions:
            return self.visit_not_conversion(tp, dynamic)
        else:
            with self._replace_conversions(None):
                return self.visit_not_conversion(tp, dynamic)

    def visit_with_conversions(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(tp)


@cache
def self_deserialization_wrapper(cls: Type) -> Type:
    return new_class(
        f"{cls.__name__}SelfDeserializer",
        (cls[cls.__parameters__] if has_type_vars(cls) else cls,),
        exec_body=lambda ns: ns.update(
            {
                "__new__": lambda _, *args, **kwargs: cls(*args, **kwargs),
                SELF_CONVERSION_ATTR: True,
            }
        ),
    )


def merge_prev_conversions(
    conversion: ResolvedConversion, prev_conversions: Conversions
) -> ResolvedConversion:
    if not conversion.sub_conversions:
        return conversion
    else:
        # Use lazy conversions to "flat" Conversions inside a Conversions list
        sub_conversions = (
            LazyConversion(lambda: conversion.sub_conversions),
            LazyConversion(lambda: prev_conversions),
        )
        return ResolvedConversion(replace(conversion, sub_conversions=sub_conversions))


class DeserializationVisitor(ConversionsVisitor[Deserialization, Return]):
    operation = OperationKind.DESERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: AnyType, conversions: ResolvedConversions
    ) -> Union[Deserialization, None, UndefinedType]:
        origin = get_origin_or_type(tp)
        identity_conv = False
        result = []
        for conv in conversions:
            conv = handle_identity_conversion(conv, tp)
            if issubclass(get_origin_or_type(conv.target), origin):
                if is_identity(conv):
                    if identity_conv:
                        continue
                    identity_conv = True
                    wrapper: AnyType = self_deserialization_wrapper(origin)
                    if get_args(tp):
                        wrapper = wrapper[get_args(tp)]
                    result.append(ResolvedConversion(replace(conv, source=wrapper)))
                else:
                    result.append(conv)
        result = list(map(handle_dataclass_model, result))
        result = [update_generics(conv, tp, as_target=True) for conv in result]
        return Undefined if identity_conv and len(result) == 1 else result or None

    _default_conversions = staticmethod(_deserializers.get)  # type: ignore

    def _handle_container_sub_conversions(
        self, conversion: Deserialization
    ) -> Deserialization:
        return [merge_prev_conversions(conv, self._conversions) for conv in conversion]

    def visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> Return:
        return self._union_result(
            self.visit_with_conversions(conv.source, conv.sub_conversions)
            for conv in conversion
        )


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
    operation = OperationKind.SERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: AnyType, conversions: ResolvedConversions
    ) -> Union[Serialization, None, UndefinedType]:
        origin = get_origin_or_type(tp)
        for conv in conversions:
            conv = handle_identity_conversion(conv, tp)
            if issubclass(origin, get_origin_or_type(conv.source)):
                if is_identity(conv):
                    return Undefined
                else:
                    return update_generics(
                        handle_dataclass_model(conv), tp, as_source=True
                    )
        else:
            return None

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        for sub_cls in tp.__mro__:
            if sub_cls in _serializers:
                conversion = _serializers[sub_cls]
                if (
                    sub_cls == tp
                    or not isinstance(conversion, Conversion)
                    or conversion.inherited is None
                    or conversion.inherited
                ):
                    return conversion
        else:
            return None

    def _handle_container_sub_conversions(
        self, conversion: Serialization
    ) -> Serialization:
        return merge_prev_conversions(conversion, self._conversions)

    def visit_conversion(
        self, tp: AnyType, conversion: Serialization, dynamic: bool
    ) -> Return:
        return self.visit_with_conversions(
            conversion.target, conversion.sub_conversions
        )


class DynamicConversionResolver(ConversionsVisitor[Conv, Optional[AnyType]]):
    def __init__(self):
        super().__init__()
        self._rec_guard: Set[Tuple[AnyType, ResolvedConversions]] = set()

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Optional[AnyType]:
        result = self.visit(tp)
        return Annotated[(result, *annotations)]

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Optional[AnyType]:
        value = self.visit(value_type)
        return None if value is None else Collection[value]  # type: ignore

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Optional[AnyType]:
        key = self.visit(key_type)
        value = self.visit(value_type)
        return None if key is None or value is None else Mapping[key, value]  # type: ignore # noqa: E501

    def visit_types(
        self, types: Iterable[AnyType], origin: AnyType
    ) -> Optional[AnyType]:
        modified = False
        types2 = []
        for tp in types:
            try:
                res = self.visit(tp)
                types2.append(res if res is not None else tp)
                modified = res is not None
            except Exception:
                types2.append(tp)
        return origin[tuple(types2)] if modified else None

    def tuple(self, types: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(types, Tuple)

    def union(self, alternatives: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(filter_skipped(alternatives, schema_only=True), Union)

    def _conversion_type(self, conversion: Conv) -> AnyType:
        raise NotImplementedError

    def _visit_dynamic(
        self, tp: AnyType, conversion: Optional[Conv], dynamic: bool
    ) -> Optional[AnyType]:
        origin = get_origin_or_type(tp)
        if (origin, self._conversions) in self._rec_guard:
            return None
        self._rec_guard.add((origin, self._conversions))
        try:
            if conversion is not None:
                result = super().visit_conversion(tp, conversion, dynamic)
            else:
                result = super().visit_not_conversion(tp, dynamic)
        except (NotImplementedError, Unsupported):
            result = None
        finally:
            self._rec_guard.remove((origin, self._conversions))
        if not dynamic or result is not None:
            return result
        elif conversion is not None:
            return self._conversion_type(conversion)
        else:
            return tp

    def visit_not_conversion(self, tp: AnyType, dynamic: bool) -> Optional[AnyType]:
        return self._visit_dynamic(tp, None, dynamic)

    def visit_conversion(
        self, tp: AnyType, conversion: Conv, dynamic: bool
    ) -> Optional[AnyType]:
        return self._visit_dynamic(tp, conversion, dynamic)

    def visit(self, tp: AnyType) -> Optional[AnyType]:
        if not self._conversions:
            return None
        return super().visit(tp)


class DynamicDeserializationResolver(DynamicConversionResolver, DeserializationVisitor):
    def _conversion_type(self, conversion: Deserialization) -> AnyType:
        return Union[tuple(conv.source for conv in conversion)]

    def visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> Optional[AnyType]:
        args = []
        modified = False
        for conv in conversion:
            try:
                res = self.visit_with_conversions(conv.source, conv.sub_conversions)
                args.append(res if res is not None else conv.source)
                modified = res is not None
            except Exception:
                args.append(conv.source)
        return Union[tuple(args)] if modified else None


class DynamicSerializationResolver(DynamicConversionResolver, SerializationVisitor):
    def _conversion_type(self, conversion: Serialization) -> AnyType:
        return conversion.target


DeserializationVisitor._dynamic_conversion_resolver = DynamicDeserializationResolver
SerializationVisitor._dynamic_conversion_resolver = DynamicSerializationResolver
