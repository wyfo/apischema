import warnings
from dataclasses import MISSING, field as field_, make_dataclass
from inspect import Parameter, iscoroutinefunction, signature
from typing import Any, Callable, Mapping, Tuple, Type

from apischema.metadata import properties
from apischema.typing import get_type_hints
from apischema.utils import to_camel_case


def dataclass_input_wrapper(
    func: Callable, parameters_metadata: Mapping[str, Mapping] = None
) -> Tuple[Callable, Type]:
    warnings.warn(
        "dataclass_input_wrapper is deprecated, use object_deserialization instead",
        DeprecationWarning,
    )
    parameters_metadata = parameters_metadata or {}
    types = get_type_hints(func, include_extras=True)
    fields = []
    params, kwargs_param = [], None
    for param_name, param in signature(func).parameters.items():
        if param.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError("Positional only parameters are not supported")
        field_type = types.get(param_name, Any)
        if param.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
            default = MISSING if param.default is Parameter.empty else param.default
            field = field_(
                default=default, metadata=parameters_metadata.get(param_name)
            )
            fields.append((param_name, field_type, field))
            params.append(param_name)
        if param.kind == Parameter.VAR_KEYWORD:
            field = field_(default_factory=dict, metadata=properties)
            fields.append((param_name, Mapping[str, field_type], field))  # type: ignore
            kwargs_param = param_name

    input_cls = make_dataclass(to_camel_case(func.__name__), fields)

    def wrapper(input):
        kwargs = {name: getattr(input, name) for name in params}
        if kwargs_param:
            kwargs.update(getattr(input, kwargs_param))
        return func(**kwargs)

    if iscoroutinefunction(func):
        wrapped = wrapper

        async def wrapper(input):
            return await wrapped(input)

    wrapper.__annotations__["input"] = input_cls
    if "return" in func.__annotations__:
        wrapper.__annotations__["return"] = func.__annotations__["return"]
    return wrapper, input_cls
