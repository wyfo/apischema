from dataclasses import dataclass
from types import new_class
from typing import Callable, Optional, TYPE_CHECKING, Tuple, Type, Union

from apischema.conversions import Conversion
from apischema.conversions.utils import identity
from apischema.dataclasses import replace
from apischema.utils import PREFIX, cached_property

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coercion

Model = Union[Type, Callable[[], Type]]


def check_model(origin: Type, model: Type):
    if not isinstance(model, type):
        raise TypeError("Dataclass model must be a dataclass")
    if getattr(origin, "__parameters__", ()) != getattr(model, "__parameters__", ()):
        raise TypeError("Dataclass model must have the same generic parameters")


MODEL_ORIGIN_ATTR = f"{PREFIX}model_origin"


@dataclass(frozen=True)
class DataclassModel:
    origin: Type
    model: Model
    fields_only: bool

    @cached_property
    def dataclass(self) -> Type:
        origin = self.origin
        if isinstance(self.model, type):
            assert check_model(origin, self.model) is None
            model = self.model
        else:
            model = self.model()
            check_model(origin, model)
        namespace = {"__new__": lambda _, *args, **kwargs: origin(*args, **kwargs)}
        if not self.fields_only:
            namespace[MODEL_ORIGIN_ATTR] = origin
        return new_class(
            model.__name__, (model,), exec_body=lambda ns: ns.update(namespace)
        )


def dataclass_model(
    origin: Type,
    model: Model,
    *,
    fields_only: bool = False,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coercion"] = None,
    default_fallback: Optional[bool] = None,
    exclude_unset: Optional[bool] = None,
) -> Tuple[Conversion, Conversion]:
    if isinstance(model, type):
        check_model(origin, model)

    model_type = DataclassModel(origin, model, fields_only)
    conversion = Conversion(
        identity,
        additional_properties=additional_properties,
        coercion=coercion,
        default_fallback=default_fallback,
        exclude_unset=exclude_unset,
    )
    d_conv = replace(conversion, source=model_type, target=origin)
    s_conv = replace(conversion, source=origin, target=model_type)
    return d_conv, s_conv


def has_model_origin(cls: Type) -> bool:
    return hasattr(cls, MODEL_ORIGIN_ATTR)


def get_model_origin(cls: Type) -> Type:
    return getattr(cls, MODEL_ORIGIN_ATTR)
