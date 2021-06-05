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
    AnyConversion,
    DefaultConversion,
    ResolvedConversion,
    ResolvedConversions,
    handle_identity_conversion,
    is_identity,
    resolve_any_conversion,
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
    def __init__(self, default_conversion: DefaultConversion):
        self.default_conversion = default_conversion
        self._conversions: Optional[AnyConversion] = None

    def _has_conversion(
        self, tp: AnyType, conversion: Optional[AnyConversion]
    ) -> Tuple[bool, Optional[Conv]]:
        raise NotImplementedError

    def _annotated_conversion(
        self, annotation: ConversionMetadata
    ) -> Optional[AnyConversion]:
        raise NotImplementedError

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Result:
        for annotation in reversed(annotations):
            if isinstance(annotation, ConversionMetadata):
                with self._replace_conversion(self._annotated_conversion(annotation)):
                    return super().annotated(tp, annotations)
        return super().annotated(tp, annotations)

    def _union_result(self, results: Iterable[Result]) -> Result:
        raise NotImplementedError

    def union(self, alternatives: Sequence[AnyType]) -> Result:
        return self._union_result(map(self.visit, alternatives))

    @contextmanager
    def _replace_conversion(self, conversion: Optional[AnyConversion]):
        with context_setter(self) as setter:
            setter._conversions = resolve_any_conversion(conversion)
            yield

    def visit_with_conv(
        self, tp: AnyType, conversion: Optional[AnyConversion]
    ) -> Result:
        with self._replace_conversion(conversion):
            return self.visit(tp)

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Conv,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> Result:
        raise NotImplementedError

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Conv],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> Result:
        if conversion is not None:
            return self._visit_conversion(tp, conversion, dynamic, next_conversion)
        else:
            with self._replace_conversion(next_conversion):
                return super().visit(tp)

    def visit(self, tp: AnyType) -> Result:
        if not is_convertible(tp):
            return self.visit_conversion(tp, None, False, self._conversions)
        dynamic, conversion = self._has_conversion(tp, self._conversions)
        if not dynamic:
            _, conversion = self._has_conversion(
                tp, self.default_conversion(get_origin_or_type(tp))  # type: ignore
            )
        next_conversion = None
        if not dynamic and is_subclass(tp, Collection):
            next_conversion = self._conversions
        return self.visit_conversion(tp, conversion, dynamic, next_conversion)


def sub_conversion(
    conversion: ResolvedConversion, next_conversion: Optional[AnyConversion]
) -> Optional[AnyConversion]:
    return (
        LazyConversion(lambda: conversion.sub_conversion),
        LazyConversion(lambda: next_conversion),
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
        tp: AnyType, conversion: Optional[AnyConversion]
    ) -> Tuple[bool, Optional[Deserialization]]:
        identity_conv, result = False, []
        for conv in resolve_any_conversion(conversion):
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
    ) -> Optional[AnyConversion]:
        return annotation.deserialization

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Deserialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> Result:
        return self._union_result(
            self.visit_with_conv(conv.source, sub_conversion(conv, next_conversion))
            for conv in conversion
        )


class SerializationVisitor(ConversionsVisitor[Serialization, Result]):
    @staticmethod
    def _has_conversion(
        tp: AnyType, conversion: Optional[AnyConversion]
    ) -> Tuple[bool, Optional[Serialization]]:
        for conv in resolve_any_conversion(conversion):
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
    ) -> Optional[AnyConversion]:
        return annotation.serialization

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Serialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> Result:
        return self.visit_with_conv(
            conversion.target, sub_conversion(conversion, next_conversion)
        )


class CachedConversionsVisitor(ConversionsVisitor[Conv, Result]):
    def __init__(self, default_conversion: DefaultConversion):
        super().__init__(default_conversion)
        self._visit_cache: Dict[
            Tuple[AnyType, Optional[AnyConversion], Hashable], Result
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
