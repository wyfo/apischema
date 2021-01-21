from typing import Pattern

from apischema.types import AnyType


def infer_pattern(tp: AnyType) -> Pattern:
    from apischema.json_schema.generation.schema import DeserializationSchemaBuilder

    try:
        builder = DeserializationSchemaBuilder(lambda s: s, lambda s: s, {}, False)
        prop_schema = builder.visit(tp)
    except RecursionError:
        pass
    else:
        if (
            len(prop_schema.get("patternProperties", {})) == 1
            and "additionalProperties" not in prop_schema
        ):
            return next(iter(prop_schema["patternProperties"]))
    raise TypeError("Cannot inferred pattern from type schema") from None
