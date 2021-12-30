import collections.abc
import dataclasses
import inspect
import re
from collections import defaultdict
from contextlib import contextmanager
from enum import Enum
from functools import lru_cache, partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Dict,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from apischema.aliases import Aliaser
from apischema.cache import cache
from apischema.conversions.conversions import AnyConversion, DefaultConversion
from apischema.conversions.converters import ValueErrorCatcher
from apischema.conversions.visitor import (
    Deserialization,
    DeserializationVisitor,
    sub_conversion,
)
from apischema.dependencies import get_dependent_required
from apischema.deserialization.coercion import Coerce, Coercer
from apischema.deserialization.flattened import get_deserialization_flattened_aliases
from apischema.deserialization.methods import (
    AdditionalField,
    AnyMethod,
    BoolMethod,
    CoercerMethod,
    ConstrainedFloatMethod,
    ConstrainedIntMethod,
    ConstrainedStrMethod,
    Constraint,
    Constructor,
    ConversionAlternative,
    ConversionMethod,
    ConversionUnionMethod,
    ConversionWithValueErrorMethod,
    DefaultField,
    DeserializationMethod,
    DiscriminatorMethod,
    FactoryField,
    Field,
    FieldsConstructor,
    FlattenedField,
    FloatMethod,
    IntMethod,
    ListCheckOnlyMethod,
    ListMethod,
    LiteralMethod,
    MappingCheckOnly,
    MappingMethod,
    NoConstructor,
    NoneMethod,
    ObjectMethod,
    OptionalMethod,
    PatternField,
    RawConstructor,
    RecMethod,
    SetMethod,
    SimpleObjectMethod,
    StrMethod,
    SubprimitiveMethod,
    TupleMethod,
    TypeCheckMethod,
    UnionByTypeMethod,
    UnionMethod,
    ValidatorMethod,
    VariadicTupleMethod,
)
from apischema.discriminators import Discriminator, get_inherited_discriminator
from apischema.json_schema.patterns import infer_pattern
from apischema.metadata.implem import ValidatorsMetadata
from apischema.metadata.keys import (
    DISCRIMINATOR_METADATA,
    SCHEMA_METADATA,
    VALIDATORS_METADATA,
)
from apischema.objects import ObjectField
from apischema.objects.fields import FieldKind
from apischema.objects.visitor import DeserializationObjectVisitor
from apischema.recursion import RecursiveConversionsVisitor
from apischema.schemas import Schema, get_schema
from apischema.schemas.constraints import Constraints, merge_constraints
from apischema.types import PRIMITIVE_TYPES, AnyType, NoneType
from apischema.typing import get_args, get_origin, is_type, is_typed_dict, is_union
from apischema.utils import (
    CollectionOrPredicate,
    Lazy,
    as_predicate,
    deprecate_kwargs,
    get_origin_or_type,
    literal_values,
    opt_or,
    to_pascal_case,
    to_snake_case,
)
from apischema.validation import get_validators
from apischema.validation.validators import Validator

if TYPE_CHECKING:
    from apischema.settings import ConstraintError

MISSING_PROPERTY = "missing property"
UNEXPECTED_PROPERTY = "unexpected property"

T = TypeVar("T")


Factory = Callable[[Optional[Constraints], Sequence[Validator]], DeserializationMethod]

JSON_TYPES = {dict, list, *PRIMITIVE_TYPES}
# FloatMethod can require "copy", because it can cast integer to float
CHECK_ONLY_METHODS = (
    NoneMethod,
    BoolMethod,
    IntMethod,
    StrMethod,
    ListCheckOnlyMethod,
    MappingCheckOnly,
)


def check_only(method: DeserializationMethod) -> bool:
    return (
        isinstance(method, CHECK_ONLY_METHODS)
        or (
            isinstance(method, OptionalMethod)
            and method.coercer is None
            and check_only(method.value_method)
        )
        or (
            isinstance(method, UnionMethod) and all(map(check_only, method.alt_methods))
        )
        or (
            isinstance(method, UnionByTypeMethod)
            and all(map(check_only, method.method_by_cls.values()))
        )
        or (isinstance(method, TypeCheckMethod) and check_only(method.fallback))
    )


@dataclasses.dataclass(frozen=True)
class DeserializationMethodFactory:
    factory: Factory
    cls: Optional[type] = None
    constraints: Optional[Constraints] = None
    validators: Tuple[Validator, ...] = ()

    def merge(
        self, constraints: Optional[Constraints], validators: Sequence[Validator] = ()
    ) -> "DeserializationMethodFactory":
        if constraints is None and not validators:
            return self
        return dataclasses.replace(
            self,
            constraints=merge_constraints(self.constraints, constraints),
            validators=(*validators, *self.validators),
        )

    # private intermediate method instead of decorated property because of mypy
    @lru_cache()
    def _method(self) -> DeserializationMethod:
        return self.factory(self.constraints, self.validators)  # type: ignore

    @property
    def method(self) -> DeserializationMethod:
        return self._method()


def get_constraints(schema: Optional[Schema]) -> Optional[Constraints]:
    return schema.constraints if schema is not None else None


constraint_classes = {cls.__name__: cls for cls in Constraint.__subclasses__()}


def preformat_error(
    error: "ConstraintError", constraint: Any
) -> Union[str, Callable[[Any], str]]:
    return (
        error.format(constraint)
        if isinstance(error, str)
        else partial(error, constraint)
    )


def constraints_validators(
    constraints: Optional[Constraints],
) -> Mapping[type, Tuple[Constraint, ...]]:
    from apischema import settings

    result: Dict[type, Tuple[Constraint, ...]] = defaultdict(tuple)
    if constraints is not None:
        for name, attr, metadata in constraints.attr_and_metata:
            if attr is None or attr is False:
                continue
            error = preformat_error(
                getattr(settings.errors, to_snake_case(metadata.alias)),
                attr if not isinstance(attr, type(re.compile(r""))) else attr.pattern,
            )
            constraint_cls = constraint_classes[
                to_pascal_case(metadata.alias) + "Constraint"
            ]
            result[metadata.cls] = (*result[metadata.cls], constraint_cls(error, attr))  # type: ignore
    if float in result:
        result[int] = result[float]
    return result


class DeserializationMethodVisitor(
    RecursiveConversionsVisitor[Deserialization, DeserializationMethodFactory],
    DeserializationVisitor[DeserializationMethodFactory],
    DeserializationObjectVisitor[DeserializationMethodFactory],
):
    def __init__(
        self,
        additional_properties: bool,
        aliaser: Aliaser,
        coercer: Optional[Coercer],
        default_conversion: DefaultConversion,
        discriminator: Optional[str],
        fall_back_on_default: bool,
        no_copy: bool,
        pass_through: CollectionOrPredicate[type],
    ):
        super().__init__(default_conversion)
        self.additional_properties = additional_properties
        self.aliaser = aliaser
        self.coercer = coercer
        self._discriminator = discriminator
        self.fall_back_on_default = fall_back_on_default
        self.no_copy = no_copy
        self.pass_through = pass_through
        self.pass_through_type = as_predicate(pass_through)

    def _recursive_result(
        self, lazy: Lazy[DeserializationMethodFactory]
    ) -> DeserializationMethodFactory:
        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            return RecMethod(lambda: lazy().merge(constraints, validators).method)

        return DeserializationMethodFactory(factory)

    def visit_not_recursive(self, tp: AnyType) -> DeserializationMethodFactory:
        return deserialization_method_factory(
            tp,
            self.additional_properties,
            self.aliaser,
            self.coercer,
            self._conversion,
            self.default_conversion,
            self._discriminator,
            self.fall_back_on_default,
            self.no_copy,
            self.pass_through,
        )

    @contextmanager
    def _discriminate(self, discriminator: Optional[str]):
        discriminator_save = self._discriminator
        self._discriminator = discriminator
        try:
            yield
        finally:
            self._discriminator = discriminator_save

    def discriminate(
        self, discriminator: Discriminator, types: Sequence[AnyType]
    ) -> DeserializationMethodFactory:
        mapping = {}
        for key, tp in discriminator.get_mapping(types).items():
            with self._discriminate(self.aliaser(discriminator.alias)):
                mapping[key] = self.visit(tp)

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            from apischema import settings

            return DiscriminatorMethod(
                self.aliaser(discriminator.alias),
                {key: fact.merge(constraints).method for key, fact in mapping.items()},
                settings.errors.missing_property,
                preformat_error(settings.errors.one_of, list(mapping)),
            )

        return self._factory(factory)

    def annotated(
        self, tp: AnyType, annotations: Sequence[Any]
    ) -> DeserializationMethodFactory:
        for annotation in reversed(annotations):
            if (
                isinstance(annotation, Mapping)
                and DISCRIMINATOR_METADATA in annotation
                and is_union(get_origin(tp))
            ):
                factory = self.discriminate(
                    annotation[DISCRIMINATOR_METADATA], get_args(tp)
                )
                break
        else:
            factory = super().annotated(tp, annotations)
        for annotation in reversed(annotations):
            if isinstance(annotation, Mapping):
                factory = factory.merge(
                    get_constraints(annotation.get(SCHEMA_METADATA)),
                    annotation.get(
                        VALIDATORS_METADATA, ValidatorsMetadata(())
                    ).validators,
                )
        return factory

    def _factory(
        self, factory: Factory, cls: Optional[type] = None, validation: bool = True
    ) -> DeserializationMethodFactory:
        def wrapper(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            method: DeserializationMethod
            if validation and validators:
                method = ValidatorMethod(
                    factory(constraints, ()), validators, self.aliaser
                )
            else:
                method = factory(constraints, validators)
            if cls is not None and self.coercer is not None:
                method = CoercerMethod(self.coercer, cls, method)
            return method

        return DeserializationMethodFactory(wrapper, cls)

    def any(self) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            return AnyMethod(dict(constraints_validators(constraints)))

        return self._factory(factory)

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> DeserializationMethodFactory:
        value_factory = self.visit(value_type)

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            value_method = value_factory.method
            list_constraints = constraints_validators(constraints)[list]
            method: DeserializationMethod
            if issubclass(cls, collections.abc.Set):
                return SetMethod(list_constraints, value_method)
            elif self.no_copy and check_only(value_method):
                method = ListCheckOnlyMethod(list_constraints, value_method)
            else:
                method = ListMethod(list_constraints, value_method)
            return VariadicTupleMethod(method) if isinstance(cls, tuple) else method

        return self._factory(factory, list)

    def enum(self, cls: Type[Enum]) -> DeserializationMethodFactory:
        return self.literal(list(cls))

    def literal(self, values: Sequence[Any]) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            from apischema import settings

            value_map = dict(zip(literal_values(values), values))
            return LiteralMethod(
                value_map,
                preformat_error(settings.errors.one_of, list(value_map)),
                self.coercer,
                tuple(set(map(type, value_map))),
            )

        return self._factory(factory)

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> DeserializationMethodFactory:
        key_factory, value_factory = self.visit(key_type), self.visit(value_type)

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            key_method, value_method = key_factory.method, value_factory.method
            dict_constraints = constraints_validators(constraints)[dict]
            if self.no_copy and check_only(key_method) and check_only(value_method):
                return MappingCheckOnly(dict_constraints, key_method, value_method)
            else:
                return MappingMethod(dict_constraints, key_method, value_method)

        return self._factory(factory, dict)

    def object(
        self, tp: Type, fields: Sequence[ObjectField]
    ) -> DeserializationMethodFactory:
        cls = get_origin_or_type(tp)
        with self._discriminate(None):
            field_factories = [
                self.visit_with_conv(f.type, f.deserialization).merge(
                    get_constraints(f.schema), f.validators
                )
                for f in fields
            ]

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            from apischema import settings

            alias_by_name = {field.name: self.aliaser(field.alias) for field in fields}
            requiring: Dict[str, Set[str]] = defaultdict(set)
            for f, reqs in get_dependent_required(cls).items():
                for req in reqs:
                    requiring[req].add(alias_by_name[f])
            normal_fields, flattened_fields, pattern_fields = [], [], []
            additional_field = None
            for field, field_factory in zip(fields, field_factories):
                field_method: DeserializationMethod = field_factory.method
                fall_back_on_default = (
                    field.fall_back_on_default or self.fall_back_on_default
                )
                if field.flattened:
                    flattened_aliases = get_deserialization_flattened_aliases(
                        cls, field, self.default_conversion
                    )
                    flattened_fields.append(
                        FlattenedField(
                            field.name,
                            tuple(set(map(self.aliaser, flattened_aliases))),
                            field_method,
                            fall_back_on_default,
                        )
                    )
                elif field.pattern_properties is not None:
                    field_pattern = field.pattern_properties
                    if field_pattern is ...:
                        field_pattern = infer_pattern(
                            field.type, self.default_conversion
                        )
                    assert isinstance(field_pattern, Pattern)
                    pattern_fields.append(
                        PatternField(
                            field.name,
                            field_pattern,
                            field_method,
                            fall_back_on_default,
                        )
                    )
                elif field.additional_properties:
                    additional_field = AdditionalField(
                        field.name, field_method, fall_back_on_default
                    )
                else:
                    normal_fields.append(
                        Field(
                            field.name,
                            self.aliaser(field.alias),
                            field_method,
                            field.required,
                            requiring[field.name],
                            fall_back_on_default,
                        )
                    )
            object_constraints = constraints_validators(constraints)[dict]
            all_alliases = set(alias_by_name.values())
            constructor: Constructor
            if is_typed_dict(cls):
                constructor = NoConstructor(cls)
            elif (
                settings.deserialization.override_dataclass_constructors
                and dataclasses.is_dataclass(cls)
                and "__slots__" not in cls.__dict__
                and not hasattr(cls, "__post_init__")
                and all(f.init for f in dataclasses.fields(cls))
                and cls.__new__ is object.__new__
                and (
                    cls.__setattr__ is object.__setattr__
                    or getattr(cls, dataclasses._PARAMS).frozen  # type: ignore
                )
                and (
                    list(
                        inspect.signature(cls.__init__, follow_wrapped=False).parameters
                    )
                    == [
                        "__dataclass_self__"
                        if "self" in dataclasses.fields(cls)
                        else "self"
                    ]
                    + [f.name for f in dataclasses.fields(cls)]
                )
            ):
                constructor = FieldsConstructor(
                    cls,
                    len(fields),
                    tuple(
                        DefaultField(f.name, f.default)
                        for f in dataclasses.fields(cls)
                        if f.default is not dataclasses.MISSING
                    ),
                    tuple(
                        FactoryField(f.name, f.default_factory)
                        for f in dataclasses.fields(cls)
                        if f.default_factory is not dataclasses.MISSING
                    ),
                )
            else:
                constructor = RawConstructor(cls)
            if (
                not object_constraints
                and not flattened_fields
                and not pattern_fields
                and not additional_field
                and (
                    self._discriminator is None
                    or self._discriminator in all_alliases
                    or is_typed_dict(cls)
                )
                and (is_typed_dict(cls) == self.additional_properties)
                and (not is_typed_dict(cls) or self.no_copy)
                and not validators
                and all(
                    check_only(f.method)
                    and f.alias == f.name
                    and not f.fall_back_on_default
                    and not f.required_by
                    for f in normal_fields
                )
            ):
                return SimpleObjectMethod(
                    constructor,
                    tuple(normal_fields),
                    all_alliases,
                    is_typed_dict(cls),
                    settings.errors.missing_property,
                    settings.errors.unexpected_property,
                )
            return ObjectMethod(
                constructor,
                object_constraints,
                tuple(normal_fields),
                tuple(flattened_fields),
                tuple(pattern_fields),
                additional_field,
                all_alliases,
                self.additional_properties,
                is_typed_dict(cls),
                tuple(validators),
                tuple(
                    (f.name, f.default_factory)
                    for f in fields
                    if f.kind == FieldKind.WRITE_ONLY
                ),
                {field.name for field in fields if field.post_init},
                self.aliaser,
                settings.errors.missing_property,
                settings.errors.unexpected_property,
                self._discriminator,
            )

        return self._factory(factory, dict, validation=False)

    def primitive(self, cls: Type) -> DeserializationMethodFactory:
        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            validators = constraints_validators(constraints)[cls]
            if cls is NoneType:
                return NoneMethod()
            elif cls is bool:
                return BoolMethod()
            elif cls is str:
                return ConstrainedStrMethod(validators) if validators else StrMethod()
            elif cls is int:
                return ConstrainedIntMethod(validators) if validators else IntMethod()
            elif cls is float:
                return (
                    ConstrainedFloatMethod(validators) if validators else FloatMethod()
                )
            else:
                raise NotImplementedError

        return self._factory(factory, cls)

    def subprimitive(self, cls: Type, superclass: Type) -> DeserializationMethodFactory:
        primitive_factory = self.primitive(superclass)

        def factory(
            constraints: Optional[Constraints], validators: Sequence[Validator]
        ) -> DeserializationMethod:
            method = SubprimitiveMethod(
                cls, primitive_factory.merge(constraints, validators).method
            )
            if self.pass_through_type(cls):
                return TypeCheckMethod(cls, method)
            return method

        return dataclasses.replace(primitive_factory, factory=factory)

    def tuple(self, types: Sequence[AnyType]) -> DeserializationMethodFactory:
        elt_factories = [self.visit(tp) for tp in types]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            def len_error(constraints: Constraints) -> Union[str, Callable[[Any], str]]:
                return constraints_validators(constraints)[list][0].error

            return TupleMethod(
                constraints_validators(constraints)[list],
                len_error(Constraints(min_items=len(types))),
                len_error(Constraints(max_items=len(types))),
                tuple(fact.method for fact in elt_factories),
            )

        return self._factory(factory, list)

    def union(self, types: Sequence[AnyType]) -> DeserializationMethodFactory:
        discriminator = get_inherited_discriminator(types)
        if discriminator is not None:
            return self.discriminate(discriminator, types)
        alt_factories = self._union_results(types)
        if len(alt_factories) == 1:
            return alt_factories[0]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            alt_methods = tuple(
                fact.merge(constraints).method for fact in alt_factories
            )
            # method_by_cls cannot replace alt_methods, because there could be several
            # methods for one class
            method_by_cls = dict(
                zip((f.cls for f in alt_factories if f.cls is not None), alt_methods)
            )
            if NoneType in types and len(alt_methods) == 2:
                value_method = next(
                    meth
                    for fact, meth in zip(alt_factories, alt_methods)
                    if fact.cls is not NoneType
                )
                return OptionalMethod(value_method, self.coercer)
            elif len(method_by_cls) == len(alt_factories):
                return UnionByTypeMethod(method_by_cls)
            else:
                return UnionMethod(alt_methods)

        return self._factory(factory)

    def _visit_conversion(
        self,
        tp: AnyType,
        conversion: Deserialization,
        dynamic: bool,
        next_conversion: Optional[AnyConversion],
    ) -> DeserializationMethodFactory:
        assert conversion
        conv_factories = [
            self.visit_with_conv(conv.source, sub_conversion(conv, next_conversion))
            for conv in conversion
        ]

        def factory(constraints: Optional[Constraints], _) -> DeserializationMethod:
            conv_alternatives = tuple(
                ConversionAlternative(
                    conv.converter.func
                    if isinstance(conv.converter, ValueErrorCatcher)
                    else conv.converter,
                    (fact if dynamic else fact.merge(constraints)).method,
                    isinstance(conv.converter, ValueErrorCatcher),
                )
                for conv, fact in zip(conversion, conv_factories)
            )

            if len(conv_alternatives) > 1:
                return ConversionUnionMethod(conv_alternatives)
            elif conv_alternatives[0].value_error:
                return ConversionWithValueErrorMethod(
                    conv_alternatives[0].converter, conv_alternatives[0].method
                )
            else:
                return ConversionMethod(
                    conv_alternatives[0].converter, conv_alternatives[0].method
                )

        return self._factory(factory, validation=not dynamic)

    def visit_conversion(
        self,
        tp: AnyType,
        conversion: Optional[Deserialization],
        dynamic: bool,
        next_conversion: Optional[AnyConversion] = None,
    ) -> DeserializationMethodFactory:
        factory = super().visit_conversion(tp, conversion, dynamic, next_conversion)
        if not dynamic:
            factory = factory.merge(get_constraints(get_schema(tp)), get_validators(tp))
            if get_args(tp):
                factory = factory.merge(
                    get_constraints(get_schema(get_origin(tp))),
                    get_validators(get_origin(tp)),
                )
        cls = get_origin_or_type(tp)
        if (
            is_type(cls)  # check for type first in order to have it hashable
            and cls not in JSON_TYPES  # eliminate most common types
            and self.pass_through_type(cls)
            and not is_typed_dict(cls)  # typed dict isinstance cannot be checked
        ):

            def wrapper(
                constraints: Optional[Constraints], _: Sequence[Validator]
            ) -> DeserializationMethod:
                return TypeCheckMethod(cls, factory.merge(constraints, ()).method)

            return self._factory(wrapper)
        return factory


@cache
def deserialization_method_factory(
    tp: AnyType,
    additional_properties: bool,
    aliaser: Aliaser,
    coercer: Optional[Coercer],
    conversion: Optional[AnyConversion],
    default_conversion: DefaultConversion,
    discriminator: Optional[str],
    fall_back_on_default: bool,
    no_copy: bool,
    pass_through: CollectionOrPredicate[type],
) -> DeserializationMethodFactory:
    return DeserializationMethodVisitor(
        additional_properties,
        aliaser,
        coercer,
        default_conversion,
        discriminator,
        fall_back_on_default,
        no_copy,
        pass_through,
    ).visit_with_conv(tp, conversion)


@overload
def deserialization_method(
    type: Type[T],
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> Callable[[Any], T]:
    ...


@overload
def deserialization_method(
    type: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> Callable[[Any], Any]:
    ...


def deserialization_method(
    type: AnyType,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> Callable[[Any], Any]:
    from apischema import settings

    coercer: Optional[Coercer] = None
    if callable(coerce):
        coercer = coerce
    elif opt_or(coerce, settings.deserialization.coerce):
        coercer = settings.deserialization.coercer
    pass_through = opt_or(pass_through, settings.deserialization.pass_through)
    if isinstance(pass_through, Collection) and not isinstance(pass_through, tuple):
        pass_through = tuple(pass_through)
    return (
        deserialization_method_factory(
            type,
            opt_or(additional_properties, settings.additional_properties),
            opt_or(aliaser, settings.aliaser),
            coercer,
            conversion,
            opt_or(default_conversion, settings.deserialization.default_conversion),
            None,
            opt_or(fall_back_on_default, settings.deserialization.fall_back_on_default),
            opt_or(no_copy, settings.deserialization.no_copy),
            pass_through,  # type: ignore
        )
        .merge(get_constraints(schema), tuple(map(Validator, validators)))
        .method.deserialize
    )


@overload
def deserialize(
    type: Type[T],
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> T:
    ...


@overload
def deserialize(
    type: AnyType,
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> Any:
    ...


@deprecate_kwargs(
    {
        "coercion": "coerce",
        "conversions": "conversion",
        "default_fallback": "fall_back_on_default",
    }
)
def deserialize(
    type: AnyType,
    data: Any,
    *,
    additional_properties: bool = None,
    aliaser: Aliaser = None,
    coerce: Coerce = None,
    conversion: AnyConversion = None,
    default_conversion: DefaultConversion = None,
    fall_back_on_default: bool = None,
    no_copy: bool = None,
    pass_through: CollectionOrPredicate[type] = None,
    schema: Schema = None,
    validators: Collection[Callable] = ()
) -> Any:
    return deserialization_method(
        type,
        additional_properties=additional_properties,
        aliaser=aliaser,
        coerce=coerce,
        conversion=conversion,
        default_conversion=default_conversion,
        fall_back_on_default=fall_back_on_default,
        no_copy=no_copy,
        pass_through=pass_through,
        schema=schema,
        validators=validators,
    )(data)
