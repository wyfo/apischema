from collections import defaultdict
from collections.abc import AsyncIterable, Callable, Iterator
from dataclasses import dataclass, field
from types import new_class
from typing import Annotated, Any, TypeVar, get_type_hints

import graphql

from apischema import deserializer, schema, serializer, type_name
from apischema.conversions import Conversion
from apischema.graphql import graphql_schema
from apischema.metadata import conversion
from apischema.objects import object_deserialization
from apischema.tagged_unions import Tagged, TaggedUnion, get_tagged
from apischema.utils import to_pascal_case

_alternative_constructors: dict[type, list[Callable]] = defaultdict(list)
Func = TypeVar("Func", bound=Callable)


def alternative_constructor(func: Func) -> Func:
    _alternative_constructors[get_type_hints(func)["return"]].append(func)
    return func


def rec_subclasses(cls: type) -> Iterator[type]:
    """Recursive implementation of type.__subclasses__"""
    for sub_cls in cls.__subclasses__():
        yield sub_cls
        yield from rec_subclasses(sub_cls)


Cls = TypeVar("Cls", bound=type)


def as_tagged_union(cls: Cls) -> Cls:
    def serialization() -> Conversion:
        annotations = {sub.__name__: Tagged[sub] for sub in rec_subclasses(cls)}
        namespace = {"__annotations__": annotations}
        tagged_union = new_class(
            cls.__name__, (TaggedUnion,), exec_body=lambda ns: ns.update(namespace)
        )
        return Conversion(
            lambda obj: tagged_union(**{obj.__class__.__name__: obj}),
            source=cls,
            target=tagged_union,
            # Conversion must not be inherited because it would lead to
            # infinite recursion otherwise
            inherited=False,
        )

    def deserialization() -> Conversion:
        annotations: dict[str, Any] = {}
        namespace: dict[str, Any] = {"__annotations__": annotations}
        for sub in rec_subclasses(cls):
            annotations[sub.__name__] = Tagged[sub]
            # Add tagged fields for all its alternative constructors
            for constructor in _alternative_constructors.get(sub, ()):
                # Build the alias of the field
                alias = to_pascal_case(constructor.__name__)
                # object_deserialization uses get_type_hints, but the constructor
                # return type is stringified and the class not defined yet,
                # so it must be assigned manually
                constructor.__annotations__["return"] = sub
                # Use object_deserialization to wrap constructor as deserializer
                deserialization = object_deserialization(constructor, type_name(alias))
                # Add constructor tagged field with its conversion
                annotations[alias] = Tagged[sub]
                namespace[alias] = Tagged(conversion(deserialization=deserialization))
        # Create the deserialization tagged union class
        tagged_union = new_class(
            cls.__name__, (TaggedUnion,), exec_body=lambda ns: ns.update(namespace)
        )
        return Conversion(
            lambda obj: get_tagged(obj)[1], source=tagged_union, target=cls
        )

    deserializer(lazy=deserialization, target=cls)
    serializer(lazy=serialization, source=cls)
    return cls


@as_tagged_union
class Drawing:
    def points(self) -> AsyncIterable[float]:
        raise NotImplementedError


@dataclass
class Line(Drawing):
    start: float
    stop: float
    step: float = field(default=1, metadata=schema(exc_min=0))

    async def points(self) -> AsyncIterable[float]:
        point = self.start
        while point <= self.stop:
            yield point
            point += self.step


@alternative_constructor
def sized_line(
    start: float, stop: float, size: Annotated[float, schema(min=1)]
) -> "Line":
    return Line(start=start, stop=stop, step=(stop - start) / (size - 1))


@dataclass
class Concat(Drawing):
    left: Drawing
    right: Drawing

    async def points(self) -> AsyncIterable[float]:
        async for point in self.left.points():
            yield point
        async for point in self.right.points():
            yield point


def echo(drawing: Drawing = None) -> Drawing | None:
    return drawing


drawing_schema = graphql_schema(query=[echo])
assert (
    graphql.utilities.print_schema(drawing_schema)
    == """\
type Query {
  echo(drawing: DrawingInput): Drawing
}

type Drawing {
  Line: Line
  Concat: Concat
}

type Line {
  start: Float!
  stop: Float!
  step: Float!
}

type Concat {
  left: Drawing!
  right: Drawing!
}

input DrawingInput {
  Line: LineInput
  SizedLine: SizedLineInput
  Concat: ConcatInput
}

input LineInput {
  start: Float!
  stop: Float!
  step: Float! = 1
}

input SizedLineInput {
  start: Float!
  stop: Float!
  size: Float!
}

input ConcatInput {
  left: DrawingInput!
  right: DrawingInput!
}"""
)

query = """\
{
echo(drawing: {
    Concat: {
        left: {
            SizedLine: {
                start: 0, stop: 12, size: 3
            },
        },
        right: {
            Line: {
                start: 12, stop: 13
            },
        }
    }
}) {
    Concat {
        left {
            Line {
                start stop step
            }
        }
        right {
            Line {
                start stop step
            }
        }
    }
}
}"""

assert graphql.graphql_sync(drawing_schema, query).data == {
    "echo": {
        "Concat": {
            "left": {"Line": {"start": 0.0, "stop": 12.0, "step": 6.0}},
            "right": {"Line": {"start": 12.0, "stop": 13.0, "step": 1.0}},
        }
    }
}
