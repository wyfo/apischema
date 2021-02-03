import warnings
from contextlib import contextmanager
from dataclasses import replace
from types import new_class
from typing import (
    Any,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from apischema.conversions.conversions import (
    Conversions,
    ResolvedConversion,
    ResolvedConversions,
    handle_container_conversions,
    is_identity,
    resolve_conversions,
)
from apischema.conversions.converters import _deserializers, _serializers
from apischema.conversions.dataclass_models import DataclassModel
from apischema.conversions.utils import (
    INVALID_CONVERSION_TYPES,
)
from apischema.skip import filter_skipped
from apischema.types import AnyType, COLLECTION_TYPES, MAPPING_TYPES
from apischema.typing import generic_mro, get_args, get_origin
from apischema.utils import (
    OperationKind,
    PREFIX,
    Undefined,
    UndefinedType,
    get_args2,
    get_origin_or_type,
    is_type_var,
    substitute_type_vars,
)
from apischema.visitor import Return, Visitor

try:
    from apischema.typing import Annotated
except ImportError:
    Annotated = ...  # type: ignore

Deserialization = Sequence[ResolvedConversion]
Serialization = ResolvedConversion
Conv = TypeVar("Conv", Deserialization, Serialization)

SELF_CONVERSION_ATTR = f"{PREFIX}self_conversion"


class ConversionsVisitor(Visitor[Return], Generic[Conv, Return]):
    operation: OperationKind
    _dynamic_conversion_resolver: Type["DynamicConversionResolver"]

    def __init__(self):
        super().__init__()
        self._conversions: ResolvedConversions = ()

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: ResolvedConversions
    ) -> Union[Conv, None, UndefinedType]:
        raise NotImplementedError

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        raise NotImplementedError

    @classmethod
    def get_conversions(
        cls, tp: Type, conversions: ResolvedConversions
    ) -> Tuple[Optional[Conv], bool]:
        result, dynamic = None, False
        if conversions is not None:
            result = cls._get_conversions(tp, conversions)
        if result is not None:
            dynamic = True
        else:
            default_conv = cls._default_conversions(tp)
            if default_conv:
                result = cls._get_conversions(tp, resolve_conversions(default_conv))
        return (result if result is not Undefined else None), dynamic  # type: ignore

    def _apply_dynamic_conversions(self, tp: AnyType) -> Optional[AnyType]:
        if not self._conversions:
            return None
        else:
            return self._dynamic_conversion_resolver().visit_with_conversions(
                tp, self._conversions
            )

    def visit_conversion(self, tp: AnyType, conversion: Conv, dynamic: bool) -> Return:
        raise NotImplementedError

    def visit_not_conversion(self, tp: AnyType) -> Return:
        return super().visit(tp)

    @contextmanager
    def _replace_conversions(self, conversions: Optional[Conversions]):
        conversions_save = self._conversions
        self._conversions = resolve_conversions(conversions)
        try:
            yield
        finally:
            self._conversions = conversions_save

    def visit(self, tp: AnyType) -> Return:
        origin = get_origin(tp) or tp
        if origin in INVALID_CONVERSION_TYPES or not isinstance(origin, type):
            return self.visit_not_conversion(tp)
        conversion, dynamic = self.get_conversions(origin, self._conversions)
        if conversion is None:
            with self._replace_conversions(
                handle_container_conversions(tp, None, self._conversions, dynamic)
            ):
                return self.visit_not_conversion(tp)
        else:
            return self.visit_conversion(tp, conversion, dynamic)

    @staticmethod
    def _update_generic_args(tp: AnyType, conversion: ResolvedConversion) -> AnyType:
        raise NotImplementedError

    def visit_with_conversions(
        self, tp: AnyType, conversions: Optional[Conversions]
    ) -> Return:
        with self._replace_conversions(conversions):
            return self.visit(tp)


class DeserializationVisitor(ConversionsVisitor[Deserialization, Return]):
    operation = OperationKind.DESERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: ResolvedConversions
    ) -> Union[Deserialization, None, UndefinedType]:
        origin = get_origin_or_type(tp)
        result = [
            conv
            for conv in conversions
            if issubclass(get_origin_or_type(conv.target), origin)
        ]
        for i, conv in enumerate(result):
            if is_identity(conv):
                if len(result) == 1:
                    return Undefined
                else:
                    namespace = {
                        "__new__": lambda _, *args, **kwargs: origin(*args, **kwargs),
                        SELF_CONVERSION_ATTR: True,
                    }
                    wrapper = new_class(
                        f"{origin.__name__}SelfDeserializer",
                        (tp,),
                        exec_body=lambda ns: ns.update(namespace),
                    )
                    result[i] = ResolvedConversion(
                        replace(conv, source=wrapper, target=conv.target)
                    )
        return result or None

    _default_conversions = staticmethod(_deserializers.get)  # type: ignore

    @staticmethod
    def _update_generic_args(tp: AnyType, conversion: ResolvedConversion) -> AnyType:
        source = conversion.source
        if isinstance(source, DataclassModel):
            source = source.dataclass
        if is_type_var(conversion.target):
            return substitute_type_vars(source, {conversion.target: tp})
        elif get_origin(tp) is None:
            return source
        else:
            origin = get_origin_or_type(tp)
            if get_origin(conversion.target) == Annotated:
                target = get_args(conversion.target)[0]
            else:
                target = conversion.target
            if getattr(target, "__parameters__", ()):
                target = target[target.__parameters__]
            substitution = {}
            for base in generic_mro(target):
                base_origin = get_origin_or_type(base)
                if (
                    base_origin == origin
                    or (origin in MAPPING_TYPES and base_origin in MAPPING_TYPES)
                    or (
                        origin in COLLECTION_TYPES
                        and base_origin
                        in COLLECTION_TYPES.keys() | MAPPING_TYPES.keys()
                    )
                ):
                    for base_arg, arg in zip(get_args(base), get_args2(tp)):
                        if is_type_var(base_arg):
                            substitution[base_arg] = arg
                        elif base_arg != arg:
                            warnings.warn(
                                f"Generic conversion target {conversion.target} is"
                                f" incompatible with type {tp}"
                            )
                            return source
                break
            return substitute_type_vars(source, substitution)

    def visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> Return:
        results = []
        for conv in conversion:
            results.append(
                self.visit_with_conversions(
                    self._update_generic_args(tp, conv),
                    handle_container_conversions(
                        conv.source, conv.sub_conversions, self._conversions, dynamic
                    ),
                )
            )
        return self._union_result(results)


class SerializationVisitor(ConversionsVisitor[Serialization, Return]):
    operation = OperationKind.SERIALIZATION

    @staticmethod
    def _get_conversions(
        tp: Type, conversions: ResolvedConversions
    ) -> Union[Serialization, None, UndefinedType]:
        origin = get_origin_or_type(tp)
        for conv in conversions:
            if issubclass(origin, get_origin_or_type(conv.source)):
                return Undefined if is_identity(conv) else conv
        else:
            return None

    @staticmethod
    def _default_conversions(tp: Type) -> Optional[Conversions]:
        for sub_cls in tp.__mro__:
            if sub_cls in _serializers:
                return _serializers[sub_cls]
        else:
            return None

    @staticmethod
    def _update_generic_args(tp: AnyType, conversion: ResolvedConversion) -> AnyType:
        target = conversion.target
        if isinstance(target, DataclassModel):
            target = target.dataclass
        if is_type_var(conversion.source):
            return substitute_type_vars(target, {conversion.source: tp})
        elif get_origin(tp) is None:
            return target
        else:
            source = conversion.source
            source_origin = get_origin_or_type(source)
            if getattr(source, "__parameters__", ()):
                source = source[source.__parameters__]
            substitution = {}
            for base in generic_mro(tp):
                base_origin = get_origin(base)
                if (
                    base_origin == source_origin
                    or (source_origin in MAPPING_TYPES and base_origin in MAPPING_TYPES)
                    or (
                        source_origin in COLLECTION_TYPES
                        and base_origin
                        in COLLECTION_TYPES.keys() | MAPPING_TYPES.keys()
                    )
                ):
                    for base_arg, source_arg in zip(get_args(base), get_args2(source)):
                        if is_type_var(source_arg):
                            substitution[source_arg] = base_arg
                        elif base_arg != source_arg:
                            warnings.warn(
                                f"Generic conversion source {conversion.source} is"
                                f" incompatible with type {tp}"
                            )
                            return target
                    break
            return substitute_type_vars(target, substitution)

    def visit_conversion(
        self, tp: AnyType, conversion: Serialization, dynamic: bool
    ) -> Return:
        return self.visit_with_conversions(
            self._update_generic_args(tp, conversion),
            handle_container_conversions(
                conversion.target,
                conversion.sub_conversions,
                self._conversions,
                dynamic,
            ),
        )


class DynamicConversionResolver(ConversionsVisitor[Conv, Optional[AnyType]]):
    def __init__(self):
        super().__init__()
        self._rec_guard: Set[Tuple[AnyType, ResolvedConversions]] = set()

    def annotated(self, tp: AnyType, annotations: Sequence[Any]) -> Optional[AnyType]:
        result = self.visit(tp)
        return Annotated[(result, *annotations)]

    def collection(
        self, cls: Type[Collection], value_type: AnyType
    ) -> Optional[AnyType]:
        value = self.visit(value_type)
        return None if value is None else Sequence[value]  # type: ignore

    def mapping(
        self, cls: Type[Mapping], key_type: AnyType, value_type: AnyType
    ) -> Optional[AnyType]:
        key = self.visit(key_type)
        value = self.visit(value_type)
        return None if key is None or value is None else Mapping[key, value]  # type: ignore # noqa: E501

    def visit_types(
        self, types: Iterable[AnyType], origin: AnyType
    ) -> Optional[AnyType]:
        modified = False
        types2 = []
        for tp in types:
            try:
                res = self.visit(tp)
                types2.append(res if res is not None else tp)
                modified = res is not None
            except Exception:
                types2.append(tp)
        return origin[tuple(types2)] if modified else None

    def tuple(self, types: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(types, Tuple)

    def union(self, alternatives: Sequence[AnyType]) -> Optional[AnyType]:
        return self.visit_types(filter_skipped(alternatives, schema_only=True), Union)

    def _final_type(self, tp: AnyType, conversion: Conv) -> AnyType:
        raise NotImplementedError

    def visit(self, tp: AnyType) -> Optional[AnyType]:
        # if isinstance(tp, DataclassModel):
        #     return self.visit(tp.dataclass)
        origin = get_origin(tp) or tp
        if not self._conversions or (origin, self._conversions) in self._rec_guard:
            return None
        if origin in INVALID_CONVERSION_TYPES or not isinstance(origin, type):
            return self.visit_not_conversion(tp)
        conv, dynamic = self.get_conversions(origin, self._conversions)
        if not dynamic and (conv is None and get_origin(tp) is None):
            return None
        self._rec_guard.add((origin, self._conversions))
        try:
            if conv is not None:
                result = self.visit_conversion(tp, conv, dynamic)
            else:
                result = self.visit_not_conversion(tp)
            if result is not None:
                return result
            elif conv is not None:
                return self._final_type(tp, conv)
            else:
                return tp
        except Exception:
            return self._final_type(tp, conv) if conv is not None else tp
        finally:
            self._rec_guard.remove((origin, self._conversions))


class DynamicDeserializationResolver(DynamicConversionResolver, DeserializationVisitor):
    def _final_type(self, tp: AnyType, conversion: Deserialization) -> AnyType:
        return Union[tuple(self._update_generic_args(tp, conv) for conv in conversion)]

    def visit_conversion(
        self, tp: AnyType, conversion: Deserialization, dynamic: bool
    ) -> Optional[AnyType]:
        args = []
        modified = False
        for conv in conversion:
            source = self._update_generic_args(tp, conv)
            try:
                res = self.visit_with_conversions(
                    source,
                    handle_container_conversions(
                        conv.source, conv.sub_conversions, self._conversions, dynamic
                    ),
                )
                args.append(res if res is not None else source)
                modified = res is not None
            except Exception:
                args.append(source)
        return Union[tuple(args)] if modified else None


class DynamicSerializationResolver(DynamicConversionResolver, SerializationVisitor):
    def _final_type(self, tp: AnyType, conversion: Serialization) -> AnyType:
        return self._update_generic_args(tp, conversion)


DeserializationVisitor._dynamic_conversion_resolver = DynamicDeserializationResolver
SerializationVisitor._dynamic_conversion_resolver = DynamicSerializationResolver
