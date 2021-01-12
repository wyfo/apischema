from dataclasses import dataclass
from logging import getLogger
from typing import Any

from apischema import serialize, serialized
from apischema.json_schema import serialization_schema

logger = getLogger(__name__)


def log_error(error: Exception, obj: Any, alias: str) -> None:
    logger.error(
        "Serialization error in %s.%s", type(obj).__name__, alias, exc_info=error
    )
    return None


@dataclass
class Foo:
    @serialized(error_handler=log_error)
    def bar(self) -> int:
        raise RuntimeError("Some error")


assert serialize(Foo()) == {"bar": None}  # Logs "Serialization error in Foo.bar"
assert serialization_schema(Foo) == {
    "$schema": "http://json-schema.org/draft/2019-09/schema#",
    "type": "object",
    "properties": {"bar": {"readOnly": True, "type": ["integer", "null"]}},
    "required": ["bar"],
    "additionalProperties": False,
}
