from collections import defaultdict
from dataclasses import dataclass, field
from types import new_class
from typing import (
    Annotated,
    Any,
    AsyncIterable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    TYPE_CHECKING,
    Type,
    TypeVar,
)

import graphql

from apischema import deserialize, deserializer, schema, serialize, serializer
from apischema.conversions import (
    Conversion,
    dataclass_input_wrapper,
    reset_deserializers,
)
from apischema.graphql import graphql_schema
from apischema.metadata import conversion
from apischema.tagged_unions import Tagged, TaggedUnion, get_tagged

# {cls_name: [functions]}
_alternative_constructors: Dict[str, List[Callable]] = defaultdict(list)

if TYPE_CHECKING:
    # Close enough for mypy
    alternative_constructor = staticmethod
else:

    def alternative_constructor(func):
        cls_name = func.__qualname__.rsplit(".", 2)[-2]
        _alternative_constructors[cls_name].append(func)
        return staticmethod(func)


T = TypeVar("T")


# Shortcut
def desc(description: str):
    return schema(description=description)


class TaggedSerializable:
    _deserialization_union: Type[TaggedUnion] = new_class(
        "TaggedSerializable", (TaggedUnion,)
    )
    _serialization_union: Type[TaggedUnion] = new_class(
        "TaggedSerializable", (TaggedUnion,)
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Retrieved the base class inheriting Serializable
        tagged_base, *_ = [c for c in cls.__mro__ if TaggedSerializable in c.__bases__]
        assert issubclass(tagged_base, TaggedSerializable)
        assert not _, "cannot have multiple base class inheriting directly serializable"
        # If the current class is the base Serializable, do nothing
        if tagged_base == cls:
            return

        serialization_namespace = {"__annotations__": {cls.__name__: Tagged[cls]}}
        # Create the serialization tagged union class
        serialization_union = new_class(
            f"Tagged{tagged_base.__name__}Union",
            (tagged_base._serialization_union,),
            exec_body=lambda ns: ns.update(serialization_namespace),
        )
        tagged_base._serialization_union = serialization_union
        # Register the serializer
        serializer(
            Conversion(
                lambda obj: serialization_union(**{obj.__class__.__name__: obj}),
                source=tagged_base,
                target=serialization_union,
                inherited=False,
            )
        )

        annotations = {cls.__name__: Tagged[cls]}
        deserialization_namespace = {"__annotations__": annotations}
        # Add tagged fields for all its alternative constructors
        for constructor in _alternative_constructors.get(cls.__name__, ()):
            # Deref the constructor function if it is a classmethod/staticmethod
            constructor = constructor.__get__(None, cls)
            # Build the alias of the field
            alias = (
                "".join(map(str.capitalize, constructor.__name__.split("_")))
                + cls.__name__
            )
            # dataclass_input_wrapper uses get_type_hints, but the constructor
            # return type is stringified and the class not defined yet,
            # so it must be assigned manually
            constructor.__annotations__["return"] = cls
            # Wraps the constructor and rename its input class
            wrapper, wrapper_cls = dataclass_input_wrapper(constructor)
            wrapper_cls.__name__ = alias
            # Add constructor tagged field with its conversion
            annotations[alias] = Tagged[cls]
            deserialization_namespace[alias] = Tagged(
                conversion(deserialization=wrapper)
            )
        # Create the deserialization tagged union class
        deserialization_union = new_class(
            f"Tagged{tagged_base.__name__}Union",
            (tagged_base._deserialization_union,),
            exec_body=lambda ns: ns.update(deserialization_namespace),
        )
        tagged_base._deserialization_union = deserialization_union
        # Because deserializers stack, they must be reset before being reassigned
        reset_deserializers(tagged_base)
        # Register the deserializer using get_tagged
        deserializer(
            Conversion(
                lambda obj: get_tagged(obj)[1], deserialization_union, tagged_base
            )
        )

    @classmethod
    def deserialize(cls: Type[T], serialization: Mapping[str, Any]) -> T:
        """Deserialize from a dictionary representation"""
        return deserialize(cls, serialization)

    def serialize(self) -> Mapping[str, Any]:
        """Serialize to a dictionary representation"""
        return serialize(self)


class ScanSpec(TaggedSerializable):
    def points(self) -> AsyncIterable[float]:
        """Iterate through the points of the scan"""
        raise NotImplementedError


@dataclass
class Line(ScanSpec):
    """A straight line"""

    start: Annotated[float, desc("The first point")]
    stop: float = field(metadata=desc("The last point"))
    step: float = field(
        default=1, metadata=schema(description="The step between points", exc_min=0)
    )

    async def points(self) -> AsyncIterable[float]:
        point = self.start
        while point <= self.stop:
            yield point
            point += self.step

    @alternative_constructor
    def sized(
        start: Annotated[float, desc("The first point")],
        stop: Annotated[float, desc("The last point")],
        size: Annotated[float, schema(description="Number of points", min=1)],
    ) -> "Line":
        """Alternative constructor with size instead of step"""
        return Line(start=start, stop=stop, step=(stop - start) / (size - 1))


@dataclass
class Concat(ScanSpec):
    left: ScanSpec = field(metadata=desc("First spec to produce"))
    right: ScanSpec = field(metadata=desc("Second spec to produce"))

    async def points(self) -> AsyncIterable[float]:
        async for point in self.left.points():
            yield point
        async for point in self.right.points():
            yield point


def echo(spec: ScanSpec = None) -> Optional[ScanSpec]:
    return spec


def test():
    scan_spec_schema = graphql_schema(query=[echo])
    assert (
        graphql.utilities.print_schema(scan_spec_schema)
        == '''\
type Query {
  echo(spec: ScanSpecInput): ScanSpec
}

type ScanSpec {
  Line: Line
  Concat: Concat
}

type Line {
  """The first point"""
  start: Float!

  """The last point"""
  stop: Float!

  """The step between points"""
  step: Float!
}

type Concat {
  """First spec to produce"""
  left: ScanSpec!

  """Second spec to produce"""
  right: ScanSpec!
}

input ScanSpecInput {
  Line: LineInput
  SizedLine: SizedLineInput
  Concat: ConcatInput
}

input LineInput {
  """The first point"""
  start: Float!

  """The last point"""
  stop: Float!

  """The step between points"""
  step: Float! = 1
}

input SizedLineInput {
  """The first point"""
  start: Float!

  """The last point"""
  stop: Float!

  """Number of points"""
  size: Float!
}

input ConcatInput {
  """First spec to produce"""
  left: ScanSpecInput!

  """Second spec to produce"""
  right: ScanSpecInput!
}
'''
    )

    query = """\
{
    echo(spec: {
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
}
"""

    assert graphql.graphql_sync(scan_spec_schema, query).data == {
        "echo": {
            "Concat": {
                "left": {"Line": {"start": 0.0, "stop": 12.0, "step": 6.0}},
                "right": {"Line": {"start": 12.0, "stop": 13.0, "step": 1.0}},
            }
        }
    }
