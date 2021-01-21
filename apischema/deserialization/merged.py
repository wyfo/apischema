from dataclasses import Field
from typing import Any, Iterator, Mapping, Sequence, Tuple, Type

from apischema.conversions.visitor import Deserialization, DeserializationVisitor
from apischema.dataclass_utils import get_alias, get_field_conversion, get_fields
from apischema.metadata.keys import MERGED_METADATA
from apischema.types import AnyType
from apischema.utils import OperationKind
from apischema.visitor import Unsupported


class InitMergedAliasVisitor(DeserializationVisitor[Iterator[str]]):
    def dataclass(
        self,
        cls: Type,
        types: Mapping[str, AnyType],
        fields: Sequence[Field],
        init_vars: Sequence[Field],
    ) -> Iterator[str]:
        for field in get_fields(
            fields, init_vars, operation=OperationKind.DESERIALIZATION
        ):
            if MERGED_METADATA in field.metadata:
                yield from get_init_merged_alias(cls, field, types[field.name])
            else:
                yield get_alias(field)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Iterator[str]:
        yield from ()

    def named_tuple(
        self,
        cls: Type[Tuple],
        types: Mapping[str, AnyType],
        defaults: Mapping[str, Any],
    ) -> Iterator[str]:
        yield from types

    def typed_dict(
        self, cls: Type, keys: Mapping[str, AnyType], total: bool
    ) -> Iterator[str]:
        yield from keys

    def visit_conversion(self, cls: Type, conversion: Deserialization) -> Iterator[str]:
        if len(conversion) != 1:
            raise NotImplementedError
        conv = conversion[0]
        return self.visit_with_conversions(conv.source, conv.conversions)


def get_init_merged_alias(
    cls: Type, field: Field, field_type: AnyType
) -> Iterator[str]:
    field_type, conversion = get_field_conversion(
        field, field_type, OperationKind.DESERIALIZATION
    )
    try:
        yield from InitMergedAliasVisitor().visit_with_conversions(
            field_type, conversion.conversions if conversion is not None else None
        )
    except (NotImplementedError, Unsupported):
        raise TypeError(
            f"Merged field {cls.__name__}.{field.name} must have an object type"
            f" or an unique deserializer to an object type"
        ) from None
