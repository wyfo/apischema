import warnings
from contextlib import contextmanager
from typing import Generic, Mapping, Optional, Sequence, Tuple, Type, TypeVar

from apischema.conversions.converters import (
    _deserializers,
    _extra_deserializers,
    _extra_serializers,
    _serializers,
)
from apischema.conversions.utils import (
    Conversions,
    ConverterWithConversions,
    get_parameters,
)
from apischema.type_vars import resolve_type_vars
from apischema.types import AnyType
from apischema.visitor import Return, Visitor

Conv = TypeVar("Conv")
Deserialization = Mapping[Type, ConverterWithConversions]
Serialization = Tuple[Type, ConverterWithConversions]


class ConversionsVisitor(Generic[Conv, Return], Visitor[Return]):
    def __init__(self, conversions: Optional[Conversions]):
        super().__init__()
        self.conversions = conversions

    def is_conversion(
        self, cls: Type, conversions: Optional[Conversions]
    ) -> Optional[Conv]:
        raise NotImplementedError()

    def visit_conversion(self, cls: AnyType, conversion: Conv) -> Return:
        raise NotImplementedError()

    def visit_not_conversion(self, cls: AnyType) -> Return:
        return super()._visit(cls)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self.conversions
        self.conversions = conversions
        try:
            yield
        finally:
            self.conversions = conversions_save

    def _visit(self, cls: Type) -> Return:
        if not isinstance(cls, type):
            return self.visit_not_conversion(cls)
        conversion = self.is_conversion(cls, self.conversions)
        with self._replace_conversions(None):
            if conversion is None:
                return self.visit_not_conversion(cls)
            else:
                return self.visit_conversion(cls, conversion)


def handle_generic_conversion(base: AnyType, other: AnyType) -> AnyType:
    if isinstance(other, tuple):
        type_vars, other = other
        return resolve_type_vars(other, dict(zip(type_vars, get_parameters(base))))
    else:
        return other


class DeserializationVisitor(ConversionsVisitor[Deserialization, Return]):
    @staticmethod
    def is_conversion(
        cls: Type, conversions: Optional[Conversions]
    ) -> Optional[Deserialization]:
        if conversions is not None and cls in _extra_deserializers:
            try:  # cannot use __contains__ because of defaultdict/etc.
                sources = conversions[cls]
            except KeyError:
                pass
            else:
                if not isinstance(sources, Sequence):
                    sources = [sources]
                result = {}
                for source in sources:
                    source2 = handle_generic_conversion(cls, source)
                    if source2 not in _extra_deserializers[cls]:
                        warnings.warn(f"Deserializer {source} -> {cls} doesn't exists")
                    else:
                        result[source2] = _extra_deserializers[cls][source2]
                if result:
                    return result
        return _deserializers.get(cls)


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
    @staticmethod
    def is_conversion(
        cls: Type, conversions: Optional[Conversions]
    ) -> Optional[Serialization]:
        if not hasattr(cls, "__mro__"):
            return None
        for sub_cls in cls.__mro__:
            if conversions is not None and sub_cls in _extra_serializers:
                try:  # cannot use __contains__ because of defaultdict/etc.
                    target = conversions[sub_cls]
                except KeyError:
                    pass
                else:
                    if target is sub_cls:
                        return None
                    target2 = handle_generic_conversion(sub_cls, target)
                    if target2 not in _extra_serializers[sub_cls]:
                        warnings.warn(f"Serializer {cls} -> {target} doesn't exists")
                    else:
                        return target2, _extra_serializers[sub_cls][target2]
            if sub_cls in _serializers:
                return _serializers[sub_cls]
        return None
