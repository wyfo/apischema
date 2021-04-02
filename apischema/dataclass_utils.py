import sys
from dataclasses import (  # type: ignore
    Field,
    MISSING,
    is_dataclass,
)
from itertools import chain
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Type,
)

from apischema.metadata.implem import ConversionMetadata
from apischema.metadata.keys import ALIAS_METADATA, CONVERSION_METADATA
from apischema.utils import (
    OperationKind,
)

if TYPE_CHECKING:
    from apischema.conversions.conversions import Conversions

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

if sys.version_info <= (3, 7):  # pragma: no cover
    is_dataclass_ = is_dataclass

    def is_dataclass(obj) -> bool:
        return is_dataclass_(obj) and getattr(obj, "__origin__", None) is None


def get_fields(
    fields: Sequence[Field], init_vars: Sequence[Field], operation: OperationKind
) -> Sequence[Field]:
    from apischema.metadata.keys import SKIP_METADATA

    fields_by_operation = {
        OperationKind.DESERIALIZATION: chain((f for f in fields if f.init), init_vars),
        operation.SERIALIZATION: fields,
    }[operation]
    return [f for f in fields_by_operation if SKIP_METADATA not in f.metadata]


def has_default(field: Field) -> bool:
    return field.default is not MISSING or field.default_factory is not MISSING  # type: ignore # noqa: E501


def is_required(field: Field) -> bool:
    from apischema.metadata.keys import REQUIRED_METADATA

    return REQUIRED_METADATA in field.metadata or not has_default(field)


def get_default(field: Field) -> Any:
    if field.default_factory is not MISSING:  # type: ignore
        return field.default_factory()  # type: ignore
    if field.default is not MISSING:
        return field.default
    raise NotImplementedError


def get_alias(field: Field) -> str:
    return field.metadata.get(ALIAS_METADATA, field.name)


def get_requirements(
    cls: Type,
    method: Callable[[Any], Any],
    operation: OperationKind,
) -> Any:
    return {}


def get_field_conversions(
    field: Field, operation: OperationKind
) -> Optional["Conversions"]:

    if CONVERSION_METADATA not in field.metadata:
        return None
    else:
        conversions: ConversionMetadata = field.metadata[CONVERSION_METADATA]
        return {
            OperationKind.DESERIALIZATION: conversions.deserialization,
            OperationKind.SERIALIZATION: conversions.serialization,
        }[operation]
