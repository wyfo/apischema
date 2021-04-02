from typing import Iterable, Iterator, Mapping, Sequence, Type

from apischema.conversions.visitor import DeserializationVisitor
from apischema.objects import DeserializationObjectVisitor, ObjectField
from apischema.types import AnyType
from apischema.visitor import Unsupported


class InitMergedAliasVisitor(
    DeserializationObjectVisitor[Iterator[str]], DeserializationVisitor[Iterator[str]]
):
    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Iterator[str]:
        yield from ()

    def object(self, cls: Type, fields: Sequence[ObjectField]) -> Iterator[str]:
        for field in fields:
            if field.merged:
                yield from self.visit(field.type)
            elif not field.is_aggregate:
                yield field.alias

    def _union_result(self, results: Iterable[Iterator[str]]) -> Iterator[str]:
        results = list(results)
        if len(results) != 1:
            raise NotImplementedError
        return results[0]


def get_deserialization_merged_aliases(cls: Type, field: ObjectField) -> Iterator[str]:
    assert field.merged
    try:
        yield from InitMergedAliasVisitor().visit_with_conversions(
            field.type, field.deserialization
        )
    except (NotImplementedError, Unsupported):
        raise TypeError(
            f"Merged field {cls.__name__}.{field.name} must have an object type"
        ) from None
