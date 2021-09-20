from dataclasses import dataclass

from apischema import deserialize, deserializer
from apischema.json_schema import deserialization_schema


@dataclass
class Expression:
    value: int


@deserializer
def evaluate_expression(expr: str) -> Expression:
    return Expression(int(eval(expr)))


# Could be shorten into deserializer(Expression), because class is callable too
@deserializer
def expression_from_value(value: int) -> Expression:
    return Expression(value)


assert deserialization_schema(Expression) == {
    "$schema": "http://json-schema.org/draft/2020-12/schema#",
    "type": ["string", "integer"],
}
assert deserialize(Expression, 0) == deserialize(Expression, "1 - 1") == Expression(0)
