from contextlib import contextmanager
from dataclasses import replace
from functools import lru_cache
from types import new_class
from typing import (
    Any,
    Collection,
    Dict,
    Generic,
    Hashable,
    Iterable,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from apischema.conversions import LazyConversion
from apischema.conversions.conversions import (
    Conversions,
    DefaultConversions,
    ResolvedConversion,
    ResolvedConversions,
    handle_identity_conversion,
    is_identity,
    resolve_conversions,
)
from apischema.conversions.dataclass_models import handle_dataclass_model
from apischema.conversions.utils import is_convertible
from apischema.metadata.implem import ConversionMetadata
from apischema.type_names import type_name
from apischema.types import AnyType
from apischema.typing import get_args
from apischema.utils import (
    Lazy,
    context_setter,
    get_origin_or_type,
    has_type_vars,
    is_hashable,
    is_subclass,
    substitute_type_vars,
    subtyping_substitution,
)
from apischema.visitor import Result, Visitor

Deserialization = ResolvedConversions
Serialization = ResolvedConversion
Conv = TypeVar("Conv")


class ConversionsVisitor(Visitor[Result], Generic[Conv, Result]):
    def __init__(self, default_conversions: DefaultConversions):
        self.default_conversions = default_conversions
        self._conversions: Optional[Conversions] = None

    def _has_conversion(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Tuple[bool, Optional[Conv]]:
        raise NotImplementedError

    def _annotated_conversion(
        self, annotation: ConversionMetadata
    ) -> Optional[Conversions]:
        raise NotImplementedError

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Result:
        for annotation in reversed(annotations):
            if isinstance(annotation, ConversionMetadata):
                with self._replace_conversions(self._annotated_conversion(annotation)):
                    return super().annotated(tp, annotations)
        return super().annotated(tp, annotations)

    def _union_result(self, results: Iterable[Result]) -> Result:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Result:
        return self._union_result(map(self.visit, alternatives))

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        with context_setter(self) as setter:
            setter._conversions = resolve_conversions(conversions)
            yield

    def visit_with_conv(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Result:
        with self._replace_conversions(conversions):
            return self.visit(tp)

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Conv,
        dynamic: bool,
        next_conversions: Optional[Conversions],
    ) -> Result:
        raise NotImplementedError

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Conv],
        dynamic: bool,
        next_conversions: Optional[Conversions] = None,
    ) -> Result:
        if conversion is not None:
            return self._visit_conversion(tp, conversion, dynamic, next_conversions)
        else:
            with self._replace_conversions(next_conversions):
                return super().visit(tp)

    def visit(self, tp: AnyType) -> Result:
        if not is_convertible(tp):
            return self.visit_conversion(tp, None, False, self._conversions)
        dynamic, conversion = self._has_conversion(tp, self._conversions)
        if not dynamic:
            _, conversion = self._has_conversion(
                tp, self.default_conversions(get_origin_or_type(tp))  # type: ignore
            )
        next_conversions = None
        if not dynamic and is_subclass(tp, Collection):
            next_conversions = self._conversions
        return self.visit_conversion(tp, conversion, dynamic, next_conversions)


def sub_conversions(
    conversion: ResolvedConversion, next_conversions: Optional[Conversions]
) -> Optional[Conversions]:
    return (
        LazyConversion(lambda: conversion.sub_conversions),
        LazyConversion(lambda: next_conversions),
    )


@lru_cache(maxsize=0)
def self_deserialization_wrapper(cls: Type) -> Type:
    wrapper = new_class(
        f"{cls.__name__}SelfDeserializer",
        (cls[cls.__parameters__] if has_type_vars(cls) else cls,),
        exec_body=lambda ns: ns.update(
            {"__new__": lambda _, *args, **kwargs: cls(*args, **kwargs)}
        ),
    )
    return type_name(None)(wrapper)


class DeserializationVisitor(ConversionsVisitor[Deserialization, Result]):
    @staticmethod
    def _has_conversion(
        tp: AnyType, conversions: Optional[Conversions]
    ) -> Tuple[bool, Optional[Deserialization]]:
        identity_conv, result = False, []
        for conv in resolve_conversions(conversions):
            conv = handle_identity_conversion(conv, tp)
            if is_subclass(conv.target, tp):
                if is_identity(conv):
                    if identity_conv:
                        continue
                    identity_conv = True
                    wrapper: AnyType = self_deserialization_wrapper(
                        get_origin_or_type(tp)
                    )
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
            return True, None
        else:
            return bool(result), tuple(result) or None

    def _annotated_conversion(
        self, annotation: ConversionMetadata
    ) -> Optional[Conversions]:
        return annotation.deserialization

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Deserialization,
        dynamic: bool,
        next_conversions: Optional[Conversions],
    ) -> Result:
        return self._union_result(
            self.visit_with_conv(conv.source, sub_conversions(conv, next_conversions))
            for conv in conversion
        )


class SerializationVisitor(ConversionsVisitor[Serialization, Result]):
    @staticmethod
    def _has_conversion(
        tp: AnyType, conversions: Optional[Conversions]
    ) -> Tuple[bool, Optional[Serialization]]:
        for conv in resolve_conversions(conversions):
            conv = handle_identity_conversion(conv, tp)
            if is_subclass(tp, conv.source):
                if is_identity(conv):
                    return True, None
                conv = handle_dataclass_model(conv)
                substitution, _ = subtyping_substitution(conv.source, tp)
                target = substitute_type_vars(conv.target, substitution)
                return True, ResolvedConversion(replace(conv, source=tp, target=target))
        else:
            return False, None

    def _annotated_conversion(
        self, annotation: ConversionMetadata
    ) -> Optional[Conversions]:
        return annotation.serialization

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Serialization,
        dynamic: bool,
        next_conversions: Optional[Conversions],
    ) -> Result:
        return self.visit_with_conv(
            conversion.target, sub_conversions(conversion, next_conversions)
        )


class CachedConversionsVisitor(ConversionsVisitor[Conv, Result]):
    def __init__(self, default_conversions: DefaultConversions):
        super().__init__(default_conversions)
        self._visit_cache: Dict[
            Tuple[AnyType, Optional[Conversions], Hashable], Result
        ] = {}

    def _cache_key(self) -> Hashable:
        return None

    def _cache_result(self, lazy: Lazy[Result]) -> Result:
        raise NotImplementedError

    def visit(self, tp: AnyType) -> Result:
        if not is_hashable(tp):
            return super().visit(tp)
        cache_key = (tp, self._conversions, self._cache_key())
        if cache_key in self._visit_cache:
            return self._visit_cache[cache_key]
        result = None

        def lazy_result():
            assert result is not None
            return result

        self._visit_cache[cache_key] = self._cache_result(lazy_result)
        try:
            result = super().visit(tp)
        finally:
            del self._visit_cache[cache_key]
        return result
