from dataclasses import dataclass, is_dataclass
from typing import Callable, Type, Union

from apischema.cache import cache
from apischema.conversions.converters import (
    deserializer,
    extra_deserializer,
    extra_serializer,
    serializer,
)
from apischema.conversions.utils import identity
from apischema.utils import PREFIX

MODEL_ORIGIN_ATTR = f"{PREFIX}apischema"


Model = Union[Type, Callable[[], Type]]


@dataclass(frozen=True)
class DataclassModelWrapper:
    cls: Type
    model: Model


@cache
def get_model(cls: Type, model: Model) -> Type:
    if not isinstance(model, type):
        model = model()

    if not is_dataclass(model):
        raise TypeError("Dataclass model must be a dataclass")
    if len(getattr(cls, "__parameters__", ())) != len(
        getattr(model, "__parameters__", ())
    ):
        raise TypeError("Dataclass model must have the same generic parameters")
    base = model[cls.__parameters__] if hasattr(cls, "__parameters__") else model

    def __new__(_, *args, **kwargs):
        return cls(*args, **kwargs)

    return type(model.__name__, (base,), {"__new__": __new__, MODEL_ORIGIN_ATTR: cls})


def dataclass_model(
    cls: Type, *, deserialization=True, serialization=True, extra=False
) -> Callable[[Model], DataclassModelWrapper]:
    def decorator(model: Model) -> DataclassModelWrapper:
        wrapped_model = DataclassModelWrapper(cls, model)
        if deserialization:
            if extra:
                extra_deserializer(identity, wrapped_model, cls)
            else:
                deserializer(identity, wrapped_model, cls)
        if serialization:
            if extra:
                extra_serializer(identity, cls, wrapped_model)
            else:
                serializer(identity, cls, wrapped_model)

        return wrapped_model

    return decorator


def get_model_origin(cls: Type) -> Type:
    return getattr(cls, MODEL_ORIGIN_ATTR, cls)
