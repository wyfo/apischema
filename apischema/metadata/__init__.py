__all__ = [
    "alias",
    "conversion",
    "default_as_set",
    "fall_back_on_default",
    "flatten",
    "init_var",
    "none_as_undefined",
    "order",
    "post_init",
    "properties",
    "required",
    "schema",
    "skip",
    "validators",
]

import sys
import warnings

from apischema.aliases import alias
from apischema.ordering import order
from apischema.schemas import schema

from .implem import (
    conversion,
    default_as_set,
    fall_back_on_default,
    flatten,
    init_var,
    none_as_undefined,
    post_init,
    properties,
    required,
    skip,
    validators,
)

if sys.version_info >= (3, 7):

    def __getattr__(name):
        for deprecated in ("merged", "flattened"):
            if name == deprecated:
                warnings.warn(
                    f"apischema.metadata.{deprecated} is deprecated, "
                    "use apischema.metadata.flatten instead",
                    DeprecationWarning,
                )
                return flatten
            raise AttributeError(f"module {__name__} has no attribute {name}")

else:
    from .implem import flattened, merged  # noqa: F401
