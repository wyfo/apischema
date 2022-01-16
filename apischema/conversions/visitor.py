from contextlib import contextmanager, suppress
from dataclasses import replace
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
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
from apischema.conversions.utils import is_convertible
from apischema.metadata.implem import ConversionMetadata
from apischema.metadata.keys import CONVERSION_METADATA
from apischema.types import AnyType
from apischema.typing import is_type_var
from apischema.utils import (
    context_setter,
    get_args2,
    get_origin_or_type,
    identity,
    is_subclass,
    substitute_type_vars,
    subtyping_substitution,
)
from apischema.visitor import Result, Unsupported, Visitor

Deserialization = ResolvedConversions
Serialization = ResolvedConversion
Conv = TypeVar("Conv")


class ConversionsVisitor(Visitor[Result], Generic[Conv, Result]):
    def __init__(self, default_conversion: DefaultConversion):
        self.default_conversion = default_conversion
        self._conversion: Optional[AnyConversion] = None

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
            if isinstance(annotation, Mapping) and CONVERSION_METADATA in annotation:
                with self._replace_conversion(
                    self._annotated_conversion(annotation[CONVERSION_METADATA])
                ):
                    return super().annotated(tp, annotations)
        return super().annotated(tp, annotations)

    def _union_results(self, types: Iterable[AnyType]) -> Sequence[Result]:
        results = []
        for alt in types:
            with suppress(Unsupported):
                results.append(self.visit(alt))
        if not results:
            raise Unsupported(Union[tuple(types)])
        return results

    def _visited_union(self, results: Sequence[Result]) -> Result:
        raise NotImplementedError

    def union(self, types: Sequence[AnyType]) -> Result:
        return self._visited_union(self._union_results(types))

    @contextmanager
    def _replace_conversion(self, conversion: Optional[AnyConversion]):
        with context_setter(self):
            self._conversion = resolve_any_conversion(conversion) or None
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
            return self.visit_conversion(tp, None, False, self._conversion)
        dynamic, conversion = self._has_conversion(tp, self._conversion)
        if not dynamic:
            _, conversion = self._has_conversion(
                tp, self.default_conversion(get_origin_or_type(tp))
            )
        next_conversion = None
        if not dynamic and is_subclass(tp, Collection) and not is_subclass(tp, str):
            next_conversion = self._conversion
        return self.visit_conversion(tp, conversion, dynamic, next_conversion)


def sub_conversion(
    conversion: ResolvedConversion, next_conversion: Optional[AnyConversion]
) -> Optional[AnyConversion]:
    return (
        LazyConversion(lambda: conversion.sub_conversion),
        LazyConversion(lambda: next_conversion),
    )


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
                    conv = ResolvedConversion(replace(conv, sub_conversion=identity))
                if is_type_var(conv.source) or any(
                    map(is_type_var, get_args2(conv.source))
                ):
                    _, substitution = subtyping_substitution(tp, conv.target)
                    conv = replace(
                        conv, source=substitute_type_vars(conv.source, substitution)
                    )
                result.append(ResolvedConversion(replace(conv, target=tp)))
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
        results = [
            self.visit_with_conv(conv.source, sub_conversion(conv, next_conversion))
            for conv in conversion
        ]
        return self._visited_union(results)


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
                if is_type_var(conv.target) or any(
                    map(is_type_var, get_args2(conv.target))
                ):
                    substitution, _ = subtyping_substitution(conv.source, tp)
                    conv = replace(
                        conv, target=substitute_type_vars(conv.target, substitution)
                    )
                return True, ResolvedConversion(replace(conv, source=tp))
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
