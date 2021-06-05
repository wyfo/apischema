from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Dict, Mapping, Optional

from apischema.conversions import Conversion, LazyConversion
from apischema.json_schema.types import JsonSchema

RefFactory = Callable[[str], str]


def ref_prefix(prefix: str) -> RefFactory:
    if not prefix.endswith("/"):
        prefix += "/"
    return lambda ref: prefix + ref


def isolate_ref(schema: Dict[str, Any]):
    if "$ref" in schema and len(schema) > 1:
        schema.setdefault("allOf", []).append({"$ref": schema.pop("$ref")})


def to_json_schema_7(schema: JsonSchema) -> Mapping[str, Any]:
    result = schema.copy()
    isolate_ref(result)
    if "$defs" in result:
        result["definitions"] = {**result.pop("$defs"), **result.get("definitions", {})}
    if "dependentRequired" in result:
        result["dependencies"] = {
            **result.pop("dependentRequired"),
            **result.get("dependencies", {}),
        }
    return result


def to_open_api_3_0(schema: JsonSchema) -> Mapping[str, Any]:
    result = schema.copy()
    for key in ("dependentRequired", "unevaluatedProperties", "$defs"):
        result.pop(key, ...)
    isolate_ref(result)
    if "null" in result.get("type", ()):
        result.setdefault("nullable", True)
        if result["type"] == "null":
            result.pop("type")
        else:
            types = [t for t in result["type"] if t != "null"]
            result["type"] = types if len(types) > 1 else types[0]
    if {"type": "null"} in result.get("anyOf", ()):
        result.setdefault("nullable", True)
        result["anyOf"] = [a for a in result["anyOf"] if a != {"type": "null"}]
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

    DRAFT_2019_09: ClassVar["JsonSchemaVersion"]
    DRAFT_7: ClassVar["JsonSchemaVersion"]
    OPEN_API_3_0: ClassVar["JsonSchemaVersion"]


JsonSchemaVersion.DRAFT_2019_09 = JsonSchemaVersion(
    "http://json-schema.org/draft/2019-09/schema#", "#/$defs/", None, False
)
JsonSchemaVersion.DRAFT_7 = JsonSchemaVersion(
    "http://json-schema.org/draft-07/schema#", "#/definitions/", to_json_schema_7, False
)
JsonSchemaVersion.OPEN_API_3_0 = JsonSchemaVersion(
    None, "#/components/schemas/", to_open_api_3_0, True
)
