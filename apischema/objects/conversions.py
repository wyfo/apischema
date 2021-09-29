import inspect
from dataclasses import Field, replace
from types import new_class
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    Mapping,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.methods import is_method, method_wrapper
from apischema.objects.fields import MISSING_DEFAULT, ObjectField, set_object_fields
from apischema.objects.getters import object_fields, parameters_as_fields
from apischema.type_names import type_name
from apischema.types import OrderedDict
from apischema.typing import get_type_hints
from apischema.utils import (
    empty_dict,
    substitute_type_vars,
    subtyping_substitution,
    to_pascal_case,
    with_parameters,
)

T = TypeVar("T")


def object_deserialization(
    func: Callable[..., T],
    *input_class_modifiers: Callable[[type], Any],
    parameters_metadata: Mapping[str, Mapping] = None,
) -> Any:
    fields = parameters_as_fields(func, parameters_metadata)
    types = get_type_hints(func, include_extras=True)
    if "return" not in types:
        raise TypeError("Object deserialization must be typed")
    return_type = types["return"]
    bases = ()
    if getattr(return_type, "__parameters__", ()):
        bases = (Generic[return_type.__parameters__],)  # type: ignore
    elif func.__name__ != "<lambda>":
        input_class_modifiers = (
            type_name(to_pascal_case(func.__name__)),
            *input_class_modifiers,
        )

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    input_cls = new_class(
        to_pascal_case(func.__name__),
        bases,
        exec_body=lambda ns: ns.update({"__init__": __init__}),
    )
    for modifier in input_class_modifiers:
        modifier(input_cls)
    set_object_fields(input_cls, fields)
    if any(f.additional_properties for f in fields):
        kwargs_param = next(f.name for f in fields if f.additional_properties)

        def wrapper(input):
            kwargs = input.kwargs.copy()
            kwargs.update(kwargs.pop(kwargs_param))
            return func(**kwargs)

    else:

        def wrapper(input):
            return func(**input.kwargs)

    wrapper.__annotations__["input"] = with_parameters(input_cls)
    wrapper.__annotations__["return"] = return_type
    return wrapper


def _fields_and_init(
    cls: type, fields_and_methods: Union[Iterable[Any], Callable[[], Iterable[Any]]]
) -> Tuple[Sequence[ObjectField], Callable[[Any, Any], None]]:
    fields = object_fields(cls, serialization=True)
    output_fields: Dict[str, ObjectField] = OrderedDict()
    methods = []
    if callable(fields_and_methods):
        fields_and_methods = fields_and_methods()
    for elt in fields_and_methods:
        if elt is ...:
            output_fields.update(fields)
            continue
        if isinstance(elt, tuple):
            elt, metadata = elt
        else:
            metadata = empty_dict
        if not isinstance(metadata, Mapping):
            raise TypeError(f"Invalid metadata {metadata}")
        if isinstance(elt, Field):
            elt = elt.name
        if isinstance(elt, str) and elt in fields:
            elt = fields[elt]
        if is_method(elt):
            elt = method_wrapper(elt)
        if isinstance(elt, ObjectField):
            if metadata:
                output_fields[elt.name] = replace(
                    elt, metadata={**elt.metadata, **metadata}, default=MISSING_DEFAULT
                )
            else:
                output_fields[elt.name] = elt
            continue
        elif callable(elt):
            types = get_type_hints(elt)
            first_param = next(iter(inspect.signature(elt).parameters))
            substitution, _ = subtyping_substitution(types.get(first_param, cls), cls)
            ret = substitute_type_vars(types.get("return", Any), substitution)
            output_fields[elt.__name__] = ObjectField(
                elt.__name__, ret, metadata=metadata
            )
            methods.append((elt, output_fields[elt.__name__]))
        else:
            raise TypeError(f"Invalid serialization member {elt} for class {cls}")

    serialized_methods = [m for m, f in methods if output_fields[f.name] is f]
    serialized_fields = list(
        output_fields.keys() - {m.__name__ for m in serialized_methods}
    )

    def __init__(self, obj):
        for field in serialized_fields:
            setattr(self, field, getattr(obj, field))
        for method in serialized_methods:
            setattr(self, method.__name__, method(obj))

    return tuple(output_fields.values()), __init__


def object_serialization(
    cls: Type[T],
    fields_and_methods: Union[Iterable[Any], Callable[[], Iterable[Any]]],
    *output_class_modifiers: Callable[[type], Any],
) -> Callable[[T], Any]:

    generic, bases = cls, ()
    if getattr(cls, "__parameters__", ()):
        generic = cls[cls.__parameters__]  # type: ignore
        bases = Generic[cls.__parameters__]  # type: ignore
    elif (
        callable(fields_and_methods)
        and fields_and_methods.__name__ != "<lambda>"
        and not getattr(cls, "__parameters__", ())
    ):
        output_class_modifiers = (
            type_name(to_pascal_case(fields_and_methods.__name__)),
            *output_class_modifiers,
        )

    def __init__(self, obj):
        _, new_init = _fields_and_init(cls, fields_and_methods)
        new_init.__annotations__ = {"obj": generic}
        output_cls.__init__ = new_init
        new_init(self, obj)

    __init__.__annotations__ = {"obj": generic}
    output_cls = new_class(
        f"{cls.__name__}Serialization",
        bases,
        exec_body=lambda ns: ns.update({"__init__": __init__}),
    )
    for modifier in output_class_modifiers:
        modifier(output_cls)
    set_object_fields(output_cls, lambda: _fields_and_init(cls, fields_and_methods)[0])

    return output_cls
