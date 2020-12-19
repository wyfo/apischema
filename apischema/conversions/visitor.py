import warnings
from contextlib import contextmanager
from typing import Any, Generic, Mapping, Optional, Sequence, Tuple, Type, TypeVar

from apischema.conversions.converters import (
    _deserializers,
    _extra_deserializers,
    _extra_serializers,
    _serializers,
)
from apischema.conversions.dataclass_models import DataclassModelWrapper, get_model
from apischema.conversions.utils import (
    Conversions,
    ConverterWithConversions,
    get_parameters,
)
from apischema.type_vars import resolve_type_vars
from apischema.types import AnyType
from apischema.utils import Operation
from apischema.visitor import Return, Visitor

Conv = TypeVar("Conv")
Deserialization = Mapping[Type, ConverterWithConversions]
Serialization = Tuple[Type, ConverterWithConversions]


class ConversionsVisitor(Visitor[Return], Generic[Conv, Return]):
    def __init__(self):
        super().__init__()
        self._conversions = None

    operation: Operation

    def _is_conversion(self, cls: Type, arg: Optional[Any]) -> Optional[Conv]:
        raise NotImplementedError()

    def is_conversion(self, cls: Type) -> Optional[Conv]:
        arg = None
        if self._conversions is not None:
            try:
                arg = self._conversions[cls]
            except KeyError:
                pass
        return self._is_conversion(cls, arg)

    def is_extra_conversions(self, cls: AnyType) -> bool:
        return (
            isinstance(cls, type)
            and self._conversions is not None
            and cls in self._conversions
            and self.is_conversion(cls) is not None
        )

    def visit_conversion(self, cls: AnyType, conversion: Conv) -> Return:
        raise NotImplementedError()

    def visit_not_conversion(self, cls: AnyType) -> Return:
        return super()._visit(cls)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self._conversions
        self._conversions = conversions
        try:
            yield
        finally:
            self._conversions = conversions_save

    def _visit(self, cls: Type) -> Return:
        if not isinstance(cls, type):
            if isinstance(cls, DataclassModelWrapper):
                return self.visit(get_model(cls.cls, cls.model))
            else:
                return self.visit_not_conversion(cls)
        conversion = self.is_conversion(cls)
        with self._replace_conversions(None):
            if conversion is not None:
                return self.visit_conversion(cls, conversion)
            else:
                return self.visit_not_conversion(cls)

    def visit_with_conversions(
        self, cls: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(cls)


def handle_generic_conversion(base: AnyType, other: AnyType) -> AnyType:
    if isinstance(other, tuple):
        type_vars, other = other
        return resolve_type_vars(other, dict(zip(type_vars, get_parameters(base))))
    else:
        return other


class DeserializationVisitor(ConversionsVisitor[Deserialization, Return]):
    operation = Operation.DESERIALIZATION

    def visit_conversion(self, cls: AnyType, conversion: Deserialization) -> Return:
        return self._union_result(
            [
                self.visit_with_conversions(source, conversions)
                for source, (_, conversions) in conversion.items()
            ]
        )

    @staticmethod
    def _is_conversion(cls: Type, source: Optional[Any]) -> Optional[Deserialization]:
        if source is cls:
            return None
        if source is not None and cls in _extra_deserializers:
            sources = source if isinstance(source, Sequence) else [source]
            result = {}
            for source in sources:
                source2 = handle_generic_conversion(cls, source)
                if source2 not in _extra_deserializers[cls]:
                    warnings.warn(f"Deserializer {source} -> {cls} doesn't exists")
                else:
                    result[source2] = _extra_deserializers[cls][source2]
            return result or None
        return _deserializers.get(cls) or None


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
    operation = Operation.SERIALIZATION

    def visit_conversion(self, cls: AnyType, conversion: Serialization) -> Return:
        target, (_, conversions) = conversion
        return self.visit_with_conversions(target, conversions)

    @staticmethod
    def _is_conversion(cls: Type, target: Optional[Any]) -> Optional[Serialization]:
        if target is cls:
            return None
        if target is not None:
            for sub_cls in cls.__mro__:
                if sub_cls in _extra_serializers:
                    target2 = handle_generic_conversion(sub_cls, target)
                    if target2 not in _extra_serializers[sub_cls]:
                        warnings.warn(f"Serializer {cls} -> {target} doesn't exists")
                    else:
                        return target2, _extra_serializers[sub_cls][target2]
        for sub_cls in cls.__mro__:
            if sub_cls in _serializers:
                return _serializers[sub_cls]
        else:
            return None
