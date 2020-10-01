from typing import (  # type: ignore
    Generic,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from apischema.conversions.converters import (
    _deserializers,
    _extra_deserializers,
    _extra_serializers,
    _serializers,
)
from apischema.conversions.utils import Conversions, ConverterWithConversions
from apischema.visitor import (
    Arg,
    Return,
    Visitor,
)

Conv = TypeVar("Conv")
Deserialization = Mapping[Type, ConverterWithConversions]
Serialization = Tuple[Type, ConverterWithConversions]


class ConversionsVisitor(Generic[Conv, Arg, Return], Visitor[Arg, Return]):
    def __init__(self, conversions: Optional[Conversions]):
        super().__init__()
        self.conversions = conversions

    @staticmethod
    def is_conversion(cls: Type, conversions: Optional[Conversions]) -> Optional[Conv]:
        raise NotImplementedError()

    def visit_conversion(self, cls: Type, conversion: Conv, arg: Arg) -> Return:
        raise NotImplementedError()

    # For typing
    def visit_not_conversion(self, cls: Type, arg: Arg) -> Return:
        ...

    visit_not_conversion = Visitor.visit_not_builtin  # noqa F811

    def visit_not_builtin(self, cls: Type, arg: Arg) -> Return:
        conversions = self.conversions
        conversion = self.is_conversion(cls, conversions)
        if conversion is None:
            self.conversions = None
            try:
                return self.visit_not_conversion(cls, arg)
            finally:
                self.conversions = conversions
        else:
            return self.visit_conversion(cls, conversion, arg)


class DeserializationVisitor(ConversionsVisitor[Deserialization, Arg, Return]):
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


class SerializationVisitor(ConversionsVisitor[Serialization, Arg, Return]):
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
