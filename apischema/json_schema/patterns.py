from dataclasses import Field as BaseField
from typing import Dict, Pattern

from apischema.dataclasses.cache import Field

_patterns: Dict[BaseField, Pattern] = {}


def infer_pattern(field: Field) -> Pattern:
    try:
        return _patterns[field.base_field]
    except KeyError:
        from apischema.json_schema.generation.builder import (
            DeserializationSchemaBuilder,
            SerializationSchemaBuilder,
        )

        for schema_builder, cls in (
            (DeserializationSchemaBuilder, field.deserialization_type),
            (SerializationSchemaBuilder, field.serialization_type),
        ):
            try:
                prop_schema = schema_builder(None, lambda s: s, {}, False).visit(cls)
                if (
                    len(prop_schema.get("patternProperties", {})) != 1
                    or "additionalProperties" in prop_schema
                ):
                    continue
                _patterns[field.base_field] = pattern = next(
                    iter(prop_schema["patternProperties"])
                )
                return pattern
            except RecursionError:
                pass
        else:
            raise TypeError("Cannot inferred pattern from type schema") from None
