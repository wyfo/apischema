from dataclasses import dataclass

from apischema.json_schema import deserialization_schema


@dataclass
class Foo:
    bar: int


def ref_factory(ref: str) -> str:
    return f"http://some-domain.org/path/to/{ref}.json#"


assert deserialization_schema(Foo, ref_factory=ref_factory, all_refs=True) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "$ref": "http://some-domain.org/path/to/Foo.json#",
}
