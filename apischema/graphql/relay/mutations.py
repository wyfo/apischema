from dataclasses import Field, MISSING, field, make_dataclass
from functools import wraps
from inspect import Parameter, signature
from typing import (
    Awaitable,
    Callable,
    ClassVar,
    Collection,
    Iterator,
    List,
    NewType,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

from graphql.pyutils import camel_to_snake

from apischema.aliases import alias
from apischema.graphql.schema import Mutation as Mutation_
from apischema.schemas import Schema
from apischema.serialization.serialized_methods import ErrorHandler
from apischema.type_names import type_name
from apischema.types import AnyType, Undefined
from apischema.typing import get_type_hints
from apischema.utils import is_async, is_union_of, wrap_generic_init_subclass

ClientMutationId = NewType("ClientMutationId", str)
type_name(None)(ClientMutationId)
CLIENT_MUTATION_ID = "client_mutation_id"
M = TypeVar("M", bound="Mutation")


class Mutation:
    _error_handler: ClassVar[ErrorHandler] = Undefined
    _schema: ClassVar[Optional[Schema]] = None
    _client_mutation_id: ClassVar[Optional[bool]] = None
    _mutation: ClassVar[Mutation_]  # set in __init_subclass__

    # Mutate is not defined to prevent Mypy warning about signature of superclass
    mutate: ClassVar[Callable]

    @wrap_generic_init_subclass
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "mutate"):
            return
        if not isinstance(cls.__dict__["mutate"], (classmethod, staticmethod)):
            raise TypeError(f"{cls.__name__}.mutate must be a classmethod/staticmethod")
        mutate = getattr(cls, "mutate")
        type_name(f"{cls.__name__}Payload")(cls)
        types = get_type_hints(mutate, localns={cls.__name__: cls}, include_extras=True)
        async_mutate = is_async(mutate, types)
        fields: List[Tuple[str, AnyType, Field]] = []
        cmi_param = None
        for param_name, param in signature(mutate).parameters.items():
            if param.kind is Parameter.POSITIONAL_ONLY:
                raise TypeError("Positional only parameters are not supported")
            if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
                if param_name not in types:
                    raise TypeError("Mutation parameters must be typed")
                field_type = types[param_name]
                field_ = MISSING if param.default is Parameter.empty else param.default
                if is_union_of(field_type, ClientMutationId):
                    cmi_param = param_name
                    if cls._client_mutation_id is False:
                        if field_ is MISSING:
                            raise TypeError(
                                "Cannot have a ClientMutationId parameter"
                                " when _client_mutation_id = False"
                            )
                        continue
                    elif cls._client_mutation_id is True:
                        field_ = MISSING
                    field_ = field(default=field_, metadata=alias(CLIENT_MUTATION_ID))
                fields.append((param_name, field_type, field_))
        field_names = [name for (name, _, _) in fields]
        if cmi_param is None and cls._client_mutation_id is not False:
            fields.append(
                (
                    CLIENT_MUTATION_ID,
                    ClientMutationId
                    if cls._client_mutation_id
                    else Optional[ClientMutationId],
                    MISSING if cls._client_mutation_id else None,
                )
            )
            cmi_param = CLIENT_MUTATION_ID
        input_cls = make_dataclass(f"{cls.__name__}Input", fields)

        def wrapper(input):
            return mutate(**{name: getattr(input, name) for name in field_names})

        wrapper.__annotations__["input"] = input_cls
        wrapper.__annotations__["return"] = Awaitable[cls] if async_mutate else cls
        if cls._client_mutation_id is not False:
            cls.__annotations__[CLIENT_MUTATION_ID] = input_cls.__annotations__[
                cmi_param
            ]
            setattr(cls, CLIENT_MUTATION_ID, field(init=False))
            wrapped = wrapper

            if async_mutate:

                async def wrapper(input):
                    result = await wrapped(input)
                    setattr(result, CLIENT_MUTATION_ID, getattr(input, cmi_param))
                    return result

            else:

                def wrapper(input):
                    result = wrapped(input)
                    setattr(result, CLIENT_MUTATION_ID, getattr(input, cmi_param))
                    return result

            wrapper = wraps(wrapped)(wrapper)

        cls._mutation = Mutation_(
            function=wrapper,
            alias=camel_to_snake(cls.__name__),
            schema=cls._schema,
            error_handler=cls._error_handler,
        )


def _mutations(cls: Type[Mutation] = Mutation) -> Iterator[Type[Mutation]]:
    for base in cls.__subclasses__():
        if hasattr(base, "_mutation"):
            yield base
            yield from _mutations(base)


def mutations() -> Collection[Mutation_]:
    return [mut._mutation for mut in _mutations()]
