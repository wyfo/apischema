import warnings
from dataclasses import dataclass
from types import new_class
from typing import TYPE_CHECKING, Callable, Optional, Tuple, Type, Union

from apischema.conversions import Conversion
from apischema.conversions.conversions import ResolvedConversion
from apischema.dataclasses import replace
from apischema.utils import PREFIX, identity

if TYPE_CHECKING:
    from apischema.deserialization.coercion import Coerce

Model = Union[Type, Callable[[], Type]]


def check_model(origin: Type, model: Type):
    if not isinstance(model, type):
        raise TypeError("Dataclass model must be a dataclass")
    if getattr(origin, "__parameters__", ()) != getattr(model, "__parameters__", ()):
        raise TypeError("Dataclass model must have the same generic parameters")


MODEL_ORIGIN_ATTR = f"{PREFIX}model_origin"

DATACLASS_ATTR = "_dataclass"


@dataclass(frozen=True)
class DataclassModel:
    origin: Type
    model: Model
    fields_only: bool

    @property
    def dataclass(self) -> Type:
        if not hasattr(self, "_dataclass"):
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
            cls = new_class(
                model.__name__, (model,), exec_body=lambda ns: ns.update(namespace)
            )
            object.__setattr__(self, "_dataclass", cls)
        return getattr(self, "_dataclass")


def dataclass_model(
    origin: Type,
    model: Model,
    *,
    fields_only: bool = False,
    additional_properties: Optional[bool] = None,
    coercion: Optional["Coerce"] = None,
    fall_back_on_default: Optional[bool] = None,
    exclude_unset: Optional[bool] = None,
) -> Tuple[Conversion, Conversion]:
    warnings.warn(
        "dataclass_model is deprecated, use set_object_fields instead",
        DeprecationWarning,
    )
    if isinstance(model, type):
        check_model(origin, model)

    model_type = DataclassModel(origin, model, fields_only)
    return Conversion(identity, source=model_type, target=origin), Conversion(
        identity, source=origin, target=model_type
    )


def has_model_origin(cls: Type) -> bool:
    return hasattr(cls, MODEL_ORIGIN_ATTR)


def get_model_origin(cls: Type) -> Type:
    return getattr(cls, MODEL_ORIGIN_ATTR)


def handle_dataclass_model(conversion: ResolvedConversion) -> ResolvedConversion:
    conv: Conversion = conversion
    if isinstance(conv.source, DataclassModel):
        conv = replace(conv, source=conv.source.dataclass)
    if isinstance(conv.target, DataclassModel):
        conv = replace(conv, target=conv.target.dataclass)
    return ResolvedConversion(conv)
