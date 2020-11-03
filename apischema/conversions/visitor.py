from contextlib import contextmanager
from typing import Generic, Mapping, Optional, Sequence, Tuple, Type, TypeVar

from apischema.conversions.converters import (
    _deserializers,
    _extra_deserializers,
    _extra_serializers,
    _serializers,
)
from apischema.conversions.utils import Conversions, ConverterWithConversions
from apischema.visitor import Return, Visitor

Conv = TypeVar("Conv")
Deserialization = Mapping[Type, ConverterWithConversions]
Serialization = Tuple[Type, ConverterWithConversions]


class ConversionsVisitor(Generic[Conv, Return], Visitor[Return]):
    def __init__(self, conversions: Optional[Conversions]):
        super().__init__()
        self.conversions = conversions

    @staticmethod
    def is_conversion(cls: Type, conversions: Optional[Conversions]) -> Optional[Conv]:
        raise NotImplementedError()

    def visit_conversion(self, cls: Type, conversion: Conv) -> Return:
        raise NotImplementedError()

    # For typing
    def visit_not_conversion(self, cls: Type) -> Return:
        ...

    _name = visit_not_conversion.__name__
    visit_not_conversion = Visitor.visit_not_builtin  # noqa F811
    visit_not_conversion.__name__ = _name
    del _name

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self.conversions
        self.conversions = conversions
        try:
            yield
        finally:
            self.conversions = conversions_save

    def visit_not_builtin(self, cls: Type) -> Return:
        conversion = self.is_conversion(cls, self.conversions)
        if conversion is None:
            with self._replace_conversions(None):
                return self.visit_not_conversion(cls)
        else:
            return self.visit_conversion(cls, conversion)


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
                try:
                    return {
                        source: _extra_deserializers[cls][source] for source in sources
                    }
                except KeyError:
                    pass
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
                    try:
                        return target, _extra_serializers[sub_cls][target]
                    except KeyError:
                        pass
            if sub_cls in _serializers:
                return _serializers[sub_cls]
        return None
