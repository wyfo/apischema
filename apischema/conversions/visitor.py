from contextlib import contextmanager
from dataclasses import replace
from types import new_class
from typing import (
    Collection,
    Generic,
    Iterable,
    Optional,
    Sequence,
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
)
from apischema.conversions.converters import _deserializers, _serializers
from apischema.conversions.dataclass_models import handle_dataclass_model
from apischema.conversions.utils import INVALID_CONVERSION_TYPES
from apischema.type_names import type_name
from apischema.types import AnyType, Undefined, UndefinedType
from apischema.typing import get_args
from apischema.utils import (
    get_origin_or_type,
    has_type_vars,
    substitute_type_vars,
    subtyping_substitution,
)
from apischema.visitor import Return, Visitor

Deserialization = ResolvedConversions
Serialization = ResolvedConversion
Conv = TypeVar("Conv")


class ConversionsVisitor(Visitor[Return], Generic[Conv, Return]):
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

    def _union_result(self, results: Iterable[Return]) -> Return:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._union_result(map(self.visit, alternatives))

    def _visit_conversion(self, tp: AnyType, conversion: Conv, dynamic: bool) -> Return:
        raise NotImplementedError

    def _visit_not_conversion(self, tp: AnyType, dynamic: bool) -> Return:
        return super().visit(tp)

    def visit_conversion(
        self, tp: AnyType, conversion: Optional[Conv], dynamic: bool
    ) -> Return:
        if conversion is not None:
            return self._visit_conversion(tp, conversion, dynamic)
        else:
            return self._visit_not_conversion(tp, dynamic)

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
            return self.visit_conversion(tp, None, False)
        conversion, dynamic = self.get_conversions(tp, self._conversions)
        reuse_conversions = not dynamic and issubclass(origin, Collection)
        if conversion is not None:
            if reuse_conversions:
                conversion = self._handle_container_sub_conversions(conversion)
            return self.visit_conversion(tp, conversion, dynamic)
        elif reuse_conversions:
            return self.visit_conversion(tp, None, dynamic)
        else:
            with self._replace_conversions(None):
                return self.visit_conversion(tp, None, dynamic)

    def visit_with_conversions(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(tp)


@cache
def self_deserialization_wrapper(cls: Type) -> Type:
    wrapper = new_class(
        f"{cls.__name__}SelfDeserializer",
        (cls[cls.__parameters__] if has_type_vars(cls) else cls,),
        exec_body=lambda ns: ns.update(
            {"__new__": lambda _, *args, **kwargs: cls(*args, **kwargs)}
        ),
    )
    return type_name(None)(wrapper)


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
                    conv = ResolvedConversion(replace(conv, source=wrapper))
                conv = handle_dataclass_model(conv)
                _, substitution = subtyping_substitution(tp, conv.target)
                source = substitute_type_vars(conv.source, substitution)
                result.append(
                    ResolvedConversion(replace(conv, source=source, target=tp))
                )
        if identity_conv and len(result) == 1:
            return Undefined
        else:
            return tuple(result) or None

    _default_conversions = staticmethod(_deserializers.get)  # type: ignore

    def _handle_container_sub_conversions(
        self, conversion: Deserialization
    ) -> Deserialization:
        return tuple(
            merge_prev_conversions(conv, self._conversions) for conv in conversion
        )

    def _visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> Return:
        return self._union_result(
            self.visit_with_conversions(conv.source, conv.sub_conversions)
            for conv in conversion
        )


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
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
                    conv = handle_dataclass_model(conv)
                    substitution, _ = subtyping_substitution(conv.source, tp)
                    target = substitute_type_vars(conv.target, substitution)
                    return ResolvedConversion(replace(conv, source=tp, target=target))
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

    def _visit_conversion(
        self, tp: AnyType, conversion: Serialization, dynamic: bool
    ) -> Return:
        return self.visit_with_conversions(
            conversion.target, conversion.sub_conversions
        )
