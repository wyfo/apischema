from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Dict, Optional

from apischema.conversions import Conversion, LazyConversion
from apischema.json_schema.types import JsonSchema, JsonType

RefFactory = Callable[[str], str]


def ref_prefix(prefix: str) -> RefFactory:
    if not prefix.endswith("/"):
        prefix += "/"
    return lambda ref: prefix + ref


def isolate_ref(schema: Dict[str, Any]):
    if "$ref" in schema and len(schema) > 1:
        schema.setdefault("allOf", []).append({"$ref": schema.pop("$ref")})


def to_json_schema_2019_09(schema: JsonSchema) -> Dict[str, Any]:
    result = schema.copy()
    if "prefixItems" in result:
        if "items" in result:
            result["additionalItems"] = result.pop("items")
        result["items"] = result["prefixItems"]
    return result


def to_json_schema_7(schema: JsonSchema) -> Dict[str, Any]:
    result = to_json_schema_2019_09(schema)
    isolate_ref(result)
    if "$defs" in result:
        result["definitions"] = {**result.pop("$defs"), **result.get("definitions", {})}
    if "dependentRequired" in result:
        result["dependencies"] = {
            **result.pop("dependentRequired"),
            **result.get("dependencies", {}),
        }
    return result


OPEN_API_3_0_UNSUPPORTED = [
    "dependentRequired",
    "unevaluatedProperties",
    "additionalItems",
]


def to_open_api_3_0(schema: JsonSchema) -> Dict[str, Any]:
    result = to_json_schema_2019_09(schema)
    for key in OPEN_API_3_0_UNSUPPORTED:
        result.pop(key, ...)
    isolate_ref(result)
    if {"type": "null"} in result.get("anyOf", ()):
        result.setdefault("nullable", True)
        result["anyOf"] = [a for a in result["anyOf"] if a != {"type": "null"}]
    if "type" in result and not isinstance(result["type"], (str, JsonType)):
        if "null" in result["type"]:
            result.setdefault("nullable", True)
        result["type"] = [t for t in result["type"] if t != "null"]
        if len(result["type"]) > 1:
            result.setdefault("anyOf", []).extend(
                {"type": t} for t in result.pop("type")
            )
        else:
            result["type"] = result["type"][0]
    if "examples" in result:
        result.setdefault("example", result.pop("examples")[0])
    if "const" in result:
        result.setdefault("enum", [result.pop("const")])
    return result


@dataclass
class JsonSchemaVersion:
    schema: Optional[str] = None
    ref_prefix: str = ""
    serialization: Optional[Callable] = None
    all_refs: bool = True
    defs: bool = True

    @property
    def conversion(self) -> Optional[Conversion]:
        if self.serialization:
            # Recursive conversion pattern
            tmp = None
            conversion = Conversion(
                self.serialization, sub_conversion=LazyConversion(lambda: tmp)
            )
            tmp = conversion
            return conversion
        else:
            return None

    @property
    def ref_factory(self) -> RefFactory:
        return ref_prefix(self.ref_prefix)

    DRAFT_2020_12: ClassVar["JsonSchemaVersion"]
    DRAFT_2019_09: ClassVar["JsonSchemaVersion"]
    DRAFT_7: ClassVar["JsonSchemaVersion"]
    OPEN_API_3_0: ClassVar["JsonSchemaVersion"]
    OPEN_API_3_1: ClassVar["JsonSchemaVersion"]


JsonSchemaVersion.DRAFT_2020_12 = JsonSchemaVersion(
    "http://json-schema.org/draft/2020-12/schema#", "#/$defs/", None, False, True
)
JsonSchemaVersion.DRAFT_2019_09 = JsonSchemaVersion(
    "http://json-schema.org/draft/2020-12/schema#",
    "#/$defs/",
    to_json_schema_2019_09,
    False,
    True,
)
JsonSchemaVersion.DRAFT_7 = JsonSchemaVersion(
    "http://json-schema.org/draft-07/schema#",
    "#/definitions/",
    to_json_schema_7,
    False,
    True,
)
JsonSchemaVersion.OPEN_API_3_0 = JsonSchemaVersion(
    None, "#/components/schemas/", to_open_api_3_0, True, False
)
JsonSchemaVersion.OPEN_API_3_1 = JsonSchemaVersion(
    None, "#/components/schemas/", None, True, False
)
