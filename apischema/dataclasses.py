from dataclasses import (  # type: ignore
    Field as BaseField,
    InitVar,
    MISSING,
    _FIELDS,
    _FIELD_CLASSVAR,
    dataclass,
    fields,
    is_dataclass,
)
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Pattern,
    Set,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from apischema.alias import ALIAS_METADATA
from apischema.conversion import (
    INPUT_METADATA,
    OUTPUT_METADATA,
    check_converter,
    handle_potential_validation,
    substitute_type_vars,
)
from apischema.properties import PROPERTIES_METADATA
from apischema.schema import (
    ANNOTATIONS_METADATA,
    Annotations,
    CONSTRAINT_METADATA,
    Constraint,
)
from apischema.types import AnyType
from apischema.typing import get_type_hints
from apischema.validation import get_validators
from apischema.validation.validator import BaseValidator, VALIDATORS_METADATA, validate

Cls = TypeVar("Cls", bound=Type)


def slotted_dataclass(cls: Cls) -> Cls:
    slots = [f.name for f in fields(cls)]
    namespace = cls.__dict__.copy()
    for slot in slots:
        namespace.pop(slot, ...)
    namespace["__slots__"] = slots
    return cast(Cls, type(cls.__name__, cls.__bases__, namespace))


class FieldKind(Enum):
    INIT = auto()
    NORMAL = auto()
    NO_INIT = auto()


@slotted_dataclass
@dataclass
class Field:
    base_field: BaseField
    name: str
    alias: str
    type: AnyType
    input_type: AnyType
    output_type: AnyType
    default: bool
    kind: FieldKind
    annotations: Optional[Annotations]
    constraint: Optional[Constraint]
    input_converter: Optional[Callable[[Any], Any]]
    output_converter: Optional[Callable[[Any], Any]]


FieldCache = Tuple[List[Field], List[Tuple[Pattern, Field]], Optional[Field]]
_input_fields: Dict[Type, FieldCache] = {}
OutputFieldCache = Tuple[List[Field], List[Field]]
_output_fields: Dict[Type, OutputFieldCache] = {}

T = TypeVar("T")


def _add_field_to_lists(obj: T, kind: FieldKind, inputs: List[T], outputs: List[T]):
    if not kind == FieldKind.INIT:
        outputs.append(obj)
    if not kind == FieldKind.NO_INIT:
        inputs.append(obj)


def cache_fields(cls: Type):
    assert is_dataclass(cls)
    types = get_type_hints(cls, include_extras=True)
    input_fields: List[Field] = []
    input_patterns: List[Tuple[Pattern, Field]] = []
    input_additional: List[Field] = []
    output_fields: List[Field] = []
    output_patterns: List[Tuple[Pattern, Field]] = []
    output_additional: List[Field] = []
    all_fields: Set[str] = set()
    for field in getattr(cls, _FIELDS).values():
        assert isinstance(field, BaseField)
        if field._field_type == _FIELD_CLASSVAR:  # type: ignore
            continue
        all_fields.add(field.name)
        type_ = types[field.name]
        if isinstance(type_, InitVar):
            type_ = type_.type  # type: ignore
            kind = FieldKind.INIT
        elif type_ is InitVar:
            raise TypeError("InitVar are not handled before Python 3.8")
        elif field.init:
            kind = FieldKind.NORMAL
        else:
            kind = FieldKind.NO_INIT
        metadata = field.metadata
        input_type, output_type = type_, type_
        input_converter, output_converter = None, None
        if INPUT_METADATA in metadata:
            param, converter = metadata[INPUT_METADATA]
            param, _ = check_converter(converter, param, ...)  # type: ignore
            param, _ = substitute_type_vars(param, ...)  # type: ignore
            _, converter = handle_potential_validation(..., converter)  # type: ignore
            if VALIDATORS_METADATA in metadata:
                validators: List[BaseValidator] = metadata[VALIDATORS_METADATA]
                conv = converter
                converter = lambda data: validate(conv(data), validators)  # noqa
            input_type, input_converter = param, converter
        if OUTPUT_METADATA in metadata:
            ret, converter = metadata[OUTPUT_METADATA]
            _, ret = check_converter(converter, ..., ret)  # type: ignore
            ret, _ = substitute_type_vars(ret, ...)  # type: ignore
            output_type, output_converter = ret, converter
        new_field = Field(
            base_field=field,
            name=field.name,
            alias=metadata.get(ALIAS_METADATA, field.name),
            type=field.type,
            input_type=input_type,
            output_type=output_type,
            default=(
                field.default is not MISSING
                or field.default_factory is not MISSING  # type: ignore
            ),
            kind=kind,
            annotations=metadata.get(ANNOTATIONS_METADATA),
            constraint=metadata.get(CONSTRAINT_METADATA),
            input_converter=input_converter,
            output_converter=output_converter,
        )
        if PROPERTIES_METADATA in metadata:
            pattern = metadata[PROPERTIES_METADATA]
            if not field.init:
                raise TypeError("properties field cannot have init=false")
            if pattern is None:
                if input_additional or output_additional:
                    raise TypeError(f"Multiple additional properties for class {cls}")
                _add_field_to_lists(
                    new_field, new_field.kind, input_additional, output_additional
                )
            else:
                _add_field_to_lists(
                    (pattern, new_field),
                    new_field.kind,
                    input_patterns,
                    output_patterns,
                )
        else:
            _add_field_to_lists(new_field, new_field.kind, input_fields, output_fields)
    _input_fields[cls] = (
        input_fields,
        input_patterns,
        input_additional[0] if input_additional else None,
    )
    _output_fields[cls] = (
        output_fields,
        [f for p, f in output_patterns] + output_additional,
    )
    for validator in get_validators(cls):
        validator.dependencies = {
            dep for dep in validator.dependencies if dep in all_fields
        }


def get_input_fields(cls: Type) -> FieldCache:
    assert is_dataclass(cls)
    try:
        return _input_fields[cls]
    except KeyError:
        cache_fields(cls)
        return _input_fields[cls]


def get_output_fields_raw(cls: Type) -> OutputFieldCache:
    assert is_dataclass(cls)
    try:
        return _output_fields[cls]
    except KeyError:
        cache_fields(cls)
        return _output_fields[cls]


def get_output_fields(cls: Type) -> FieldCache:
    fields, properties_fields = get_output_fields_raw(cls)
    pattern_fields: List[Tuple[Pattern, Field]] = []
    additional_fields = None
    for field in properties_fields:
        pattern = field.base_field.metadata[PROPERTIES_METADATA]
        if pattern is not None:
            pattern_fields.append((pattern, field))
        else:
            additional_fields = field
    return fields, pattern_fields, additional_fields
