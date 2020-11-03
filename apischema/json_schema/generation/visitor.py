from dataclasses import Field
from typing import Collection, Iterable, Mapping, Optional, Sequence, Tuple, Type

from apischema.conversions.metadata import get_field_conversions
from apischema.conversions.utils import Conversions
from apischema.conversions.visitor import (
    Conv,
    ConversionsVisitor,
    Deserialization,
    DeserializationVisitor,
    Serialization,
    SerializationVisitor,
)
from apischema.dataclass_utils import (
    Requirements,
    get_requiring,
)
from apischema.skip import filter_skipped
from apischema.types import AnyType
from apischema.typing import get_origin
from apischema.visitor import Return


class SchemaVisitor(ConversionsVisitor[Conv, Return]):
    def _dataclass_fields(
        self, cls: Type, fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Iterable[Field]:
        raise NotImplementedError()

    def _field_conversions(
        self, field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        raise NotImplementedError()

    def _visit_field_(self, field: Field, field_type: AnyType) -> Return:
        return self.visit(field_type)

    def _visit_field(self, field: Field, field_type: AnyType) -> Return:
        field_type, conversions = self._field_conversions(field, field_type)
        with self._replace_conversions(conversions):
            return self._visit_field_(field, field_type)

    def _dependent_required_(self, cls: Type) -> Requirements:
        raise NotImplementedError()

    def _dependent_required(self, cls: Type) -> Mapping[str, Collection[str]]:
        dep_req = self._dependent_required_(cls)
        return {req: sorted(dep_req[req]) for req in sorted(dep_req)}

    def _union_result(self, results: Sequence[Return]) -> Return:
        pass

    def union(self, alternatives: Sequence[AnyType]) -> Return:
        return self._union_result(
            [self.visit(cls) for cls in filter_skipped(alternatives, schema_only=True)]
        )

    def _is_conversion(self, cls: AnyType) -> bool:
        # In 3.6, GenericAlias are classes with mro
        if get_origin(cls) is not None:
            return False
        try:
            return bool(self.is_conversion(cls, self.conversions))
        except Exception:
            return False


class DeserializationSchemaVisitor(
    DeserializationVisitor[Return], SchemaVisitor[Deserialization, Return]
):
    def visit_conversion(self, cls: Type, conversion: Deserialization) -> Return:
        results = []
        for source, (_, conversions) in conversion.items():
            with self._replace_conversions(conversions):
                results.append(self.visit(source))
        return self._union_result(results)

    @staticmethod
    def _dataclass_fields(
        cls: Type, fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Iterable[Field]:
        return (*(f for f in fields if f.init), *init_vars)

    @staticmethod
    def _field_conversions(
        field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        conversions = get_field_conversions(field, field_type)
        if conversions is None:
            return field_type, None
        elif conversions.deserializer is None:
            return field_type, conversions.deserialization
        else:
            type_ = next(iter(conversions.deserialization_conversion(field_type)))
            return type_, conversions.deserialization

    @staticmethod
    def _dependent_required_(cls: Type) -> Requirements:
        return get_requiring(cls)[0]


class SerializationSchemaVisitor(
    SerializationVisitor[Return], SchemaVisitor[Serialization, Return]
):
    def visit_conversion(self, cls: Type, conversion: Serialization) -> Return:
        target, (converter, conversions) = conversion
        with self._replace_conversions(conversions):
            return self.visit(target)

    @staticmethod
    def _dataclass_fields(
        cls: Type, fields: Sequence[Field], init_vars: Sequence[Field]
    ) -> Iterable[Field]:
        return fields

    @staticmethod
    def _field_conversions(
        field: Field, field_type: AnyType
    ) -> Tuple[AnyType, Optional[Conversions]]:
        conversions = get_field_conversions(field, field_type)
        if conversions is None:
            return field_type, None
        elif conversions.serializer is None:
            return field_type, conversions.serialization
        else:
            type_, *_ = conversions.serialization_conversion(field_type)
            return type_, conversions.serialization

    @staticmethod
    def _dependent_required_(cls: Type) -> Requirements:
        return get_requiring(cls)[1]
