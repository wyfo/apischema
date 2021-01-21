from contextlib import contextmanager
from types import new_class
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.conversions.conversions import (
    Conversions,
    HashableConversions,
    ResolvedConversion,
    resolve_conversions,
    resolve_deserialization,
    resolve_serialization,
    to_hashable_conversions,
)
from apischema.conversions.converters import _deserializers, _serializers
from apischema.conversions.dataclass_models import DataclassModel
from apischema.conversions.utils import is_convertible
from apischema.dataclasses import replace
from apischema.skip import filter_skipped
from apischema.types import AnyType
from apischema.typing import get_args, get_origin
from apischema.utils import (
    OperationKind,
    Undefined,
    UndefinedType,
    get_parameters,
    substitute_type_vars,
)
from apischema.visitor import Return, Visitor

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Deserialization = Sequence[ResolvedConversion]
Serialization = ResolvedConversion
Conv = TypeVar("Conv", Deserialization, Serialization)


class ConversionsVisitor(Visitor[Return], Generic[Conv, Return]):
    operation: OperationKind
    _dynamic_conversion_resolver: Type["DynamicConversionResolver"]

    def __init__(self):
        super().__init__()
        self._conversions: Optional[HashableConversions] = None

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: Conversions
    ) -> Union[Conv, None, UndefinedType]:
        raise NotImplementedError

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        raise NotImplementedError

    @classmethod
    def get_conversions(
        cls, tp: Type, conversions: Optional[Conversions]
    ) -> Optional[Conv]:
        result = None
        if conversions is not None:
            result = cls._get_conversions(tp, conversions)
        if result is None:
            conversions = cls._default_conversions(tp)
            if conversions is not None:
                result = cls._get_conversions(tp, conversions)
        return result if result is not Undefined else None  # type: ignore

    def _apply_dynamic_conversions(self, tp: AnyType) -> Optional[AnyType]:
        if self._conversions is None:
            return None
        else:
            return self._dynamic_conversion_resolver(self._conversions).visit(tp)

    def visit_conversion(self, cls: Type, conversion: Conv) -> Return:
        raise NotImplementedError

    def visit_not_conversion(self, tp: AnyType) -> Return:
        return super()._visit(tp)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self._conversions
        self._conversions = to_hashable_conversions(conversions)
        try:
            yield
        finally:
            self._conversions = conversions_save

    def _visit(self, tp: AnyType) -> Return:
        if not is_convertible(tp):
            if isinstance(tp, DataclassModel):
                return self.visit(tp.dataclass)
            else:
                return self.visit_not_conversion(tp)
        conversion = self.get_conversions(tp, self._conversions)
        with self._replace_conversions(None):
            if conversion is not None:
                return self.visit_conversion(tp, conversion)
            else:
                return self.visit_not_conversion(tp)

    def _replace_generic_args(self, tp: AnyType) -> AnyType:
        if self._generic is not None:
            substitution = dict(
                zip(get_parameters(get_origin(self._generic)), get_args(self._generic))
            )
            return substitute_type_vars(tp, substitution)
        else:
            return tp

    def visit_with_conversions(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(tp)


class DeserializationVisitor(ConversionsVisitor[Deserialization, Return]):
    operation = OperationKind.DESERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: Conversions
    ) -> Union[Deserialization, None, UndefinedType]:
        resolved_conversions = [
            conv
            for conv in resolve_conversions(conversions, resolve_deserialization)
            if conv.target == tp
        ]
        for i, conv in enumerate(resolved_conversions):
            if conv.is_identity and conv.source == tp:
                if len(resolved_conversions) == 1:
                    return Undefined
                else:
                    namespace = {
                        "__new__": lambda _, *args, **kwargs: tp(*args, **kwargs)
                    }
                    wrapper = new_class(
                        tp.__name__, (tp,), exec_body=lambda ns: ns.update(namespace)
                    )
                    resolved_conversions[i] = replace(conv, source=wrapper)
        return resolved_conversions or None

    _default_conversions = staticmethod(_deserializers.get)  # type: ignore

    def visit_conversion(self, cls: Type, conversion: Deserialization) -> Return:
        return self._union_result(
            [
                self.visit_with_conversions(
                    self._replace_generic_args(conv.source), conv.conversions
                )
                for conv in conversion
            ]
        )


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
    operation = OperationKind.SERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: Conversions
    ) -> Union[Serialization, None, UndefinedType]:
        for conv in resolve_conversions(conversions, resolve_serialization):
            if issubclass(tp, conv.source):
                if conv.is_identity and conv.target == tp:
                    return Undefined
                return conv
        else:
            return None

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        for sub_cls in tp.__mro__:
            if sub_cls in _serializers:
                return _serializers[sub_cls]
        else:
            return None

    def visit_conversion(self, cls: Type, conversion: Serialization) -> Return:
        return self.visit_with_conversions(
            self._replace_generic_args(conversion.target), conversion.conversions
        )


class DynamicConversionResolver(ConversionsVisitor[Conv, Optional[AnyType]]):
    def __init__(self, conversions: Conversions):
        super().__init__()
        self._conversions = to_hashable_conversions(conversions)

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Optional[AnyType]:
        result = self.visit(tp)
        return Annotated[(result, *annotations)]

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Optional[AnyType]:
        value = self.visit(value_type)
        return None if value is None else Sequence[value]  # type: ignore

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
                modified = True
            except Exception:
                types2.append(tp)
        return origin[types] if modified else None

    def tuple(self, types: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(types, Tuple)

    def union(self, alternatives: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(filter_skipped(alternatives, schema_only=True), Union)

    def _final_type(self, conversion: Conv) -> Optional[AnyType]:
        raise NotImplementedError

    def _visit(self, tp: AnyType) -> Optional[AnyType]:
        if self._conversions is None or not is_convertible(tp):
            return None
        conv = self._get_conversions(tp, self._conversions)
        if conv is None or conv is Undefined:
            return None
        try:
            result = self.visit_conversion(tp, conv)
            return result if result is not None else self._final_type(conv)
        except Exception:
            return self._final_type(conv)

    def visit(self, tp: AnyType) -> Optional[AnyType]:
        try:
            return super().visit(tp)
        except Exception:
            return None


class DynamicDeserializationResolver(DynamicConversionResolver, DeserializationVisitor):
    def _final_type(self, conversion: Deserialization) -> Optional[AnyType]:
        return Union[
            tuple(self._replace_generic_args(conv.source) for conv in conversion)
        ]

    def visit_conversion(
        self, cls: Type, conversion: Deserialization
    ) -> Optional[AnyType]:
        if any(conv.lazy for conv in conversion):
            return None
        else:
            return super().visit_conversion(cls, conversion)


class DynamicSerializationResolver(DynamicConversionResolver, SerializationVisitor):
    def _final_type(self, conversion: Serialization) -> Optional[AnyType]:
        return self._replace_generic_args(conversion.target)

    def visit_conversion(
        self, cls: Type, conversion: Serialization
    ) -> Optional[AnyType]:
        if conversion.lazy:
            return None
        else:
            return super().visit_conversion(cls, conversion)


DeserializationVisitor._dynamic_conversion_resolver = DynamicDeserializationResolver
SerializationVisitor._dynamic_conversion_resolver = DynamicSerializationResolver
