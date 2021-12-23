__all__ = [
    "AnyConversion",
    "Conversion",
    "LazyConversion",
    "as_names",
    "as_str",
    "catch_value_error",
    "dataclass_input_wrapper",
    "deserializer",
    "reset_deserializers",
    "reset_serializer",
    "serializer",
]

import sys
import warnings

from .conversions import AnyConversion, Conversion, LazyConversion
from .converters import (
    as_names,
    as_str,
    catch_value_error,
    deserializer,
    reset_deserializers,
    reset_serializer,
    serializer,
)
from .wrappers import dataclass_input_wrapper

if sys.version_info >= (3, 7):

    def __getattr__(name):
        if name == "identity":
            from apischema.utils import identity  # noqa: F811

            warnings.warn(
                "apischema.conversions.identity is deprecated, "
                "use apischema.identity instead",
                DeprecationWarning,
            )
            return identity
        raise AttributeError(f"module {__name__} has no attribute {name}")

else:
    from apischema.utils import identity  # noqa: F401
