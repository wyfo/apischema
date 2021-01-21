from contextlib import contextmanager, suppress
from types import new_class
from typing import (
    Collection,
    Generic,
    Mapping,
    Optional,
    Sequence,
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
        raise NotImplementedError()

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        raise NotImplementedError()

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

    def is_dynamic_conversion(self, tp: AnyType) -> bool:
        return self._conversions is not None and self._dynamic_conversion_resolver(
            self._conversions
        ).visit(tp)

    def visit_conversion(self, cls: AnyType, conversion: Conv) -> Return:
        raise NotImplementedError()

    def visit_not_conversion(self, cls: AnyType) -> Return:
        return super()._visit(cls)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self._conversions
        self._conversions = to_hashable_conversions(conversions)
        try:
            yield
        finally:
            self._conversions = conversions_save

    def _visit(self, cls: AnyType) -> Return:
        if not is_convertible(cls):
            if isinstance(cls, DataclassModel):
                return self.visit(cls.dataclass)
            else:
                return self.visit_not_conversion(cls)
        conversion = self.get_conversions(cls, self._conversions)
        with self._replace_conversions(None):
            if conversion is not None:
                return self.visit_conversion(cls, conversion)
            else:
                return self.visit_not_conversion(cls)

    def _replace_generic_args(self, tp: AnyType) -> AnyType:
        if self._generic is not None:
            substitution = dict(
                zip(get_parameters(get_origin(self._generic)), get_args(self._generic))
            )
            return substitute_type_vars(tp, substitution)
        else:
            return tp

    def visit_with_conversions(
        self, cls: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(cls)


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

    def visit_conversion(self, cls: AnyType, conversion: Deserialization) -> Return:
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

    def visit_conversion(self, cls: AnyType, conversion: Serialization) -> Return:
        return self.visit_with_conversions(
            self._replace_generic_args(conversion.target), conversion.conversions
        )


class DynamicConversionResolver(ConversionsVisitor[Conv, bool]):
    def __init__(self, conversions: Conversions):
        super().__init__()
        self._conversions = to_hashable_conversions(conversions)

    def collection(self, cls: Type[Collection], value_type: AnyType) -> bool:
        return self.visit(value_type)

    def mapping(self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType):
        self.visit(key_type)
        self.visit(value_type)

    def tuple(self, types: Sequence[AnyType]):
        for cls in types:
            self.visit(cls)

    def union(self, alternatives: Sequence[AnyType]):
        for tp in filter_skipped(alternatives, schema_only=True):
            with suppress(Exception):
                if self.visit(tp):
                    return True

    def _visit(self, cls: AnyType) -> bool:
        return (
            is_convertible(cls)
            and self._get_conversions(cls, self._conversions) is not None  # type: ignore # noqa: E501
        )

    def visit(self, cls: AnyType) -> bool:
        try:
            return super().visit(cls)
        except Exception:
            return False


class DynamicDeserializationResolver(DynamicConversionResolver, DeserializationVisitor):
    pass


class DynamicSerializationResolver(DynamicConversionResolver, SerializationVisitor):
    pass


DeserializationVisitor._dynamic_conversion_resolver = DynamicDeserializationResolver
SerializationVisitor._dynamic_conversion_resolver = DynamicSerializationResolver
