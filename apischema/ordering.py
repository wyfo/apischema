from collections import defaultdict
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    TypeVar,
    overload,
)

from apischema.cache import CacheAwareDict
from apischema.metadata.keys import ORDERING_METADATA
from apischema.types import MetadataMixin
from apischema.utils import stop_signature_abuse

Cls = TypeVar("Cls", bound=type)


@dataclass(frozen=True)
class Ordering(MetadataMixin):
    key = ORDERING_METADATA
    order: Optional[int] = None
    after: Optional[Any] = None
    before: Optional[Any] = None

    def __post_init__(self):
        from apischema.objects.fields import check_field_or_name

        if self.after is not None:
            check_field_or_name(self.after, methods=True)
        if self.before is not None:
            check_field_or_name(self.before, methods=True)


_order_overriding: MutableMapping[type, Mapping[Any, Ordering]] = CacheAwareDict({})


@overload
def order(__value: int) -> Ordering:
    ...


@overload
def order(*, after: Any) -> Ordering:
    ...


@overload
def order(*, before: Any) -> Ordering:
    ...


@overload
def order(__fields: Sequence[Any]) -> Callable[[Cls], Cls]:
    ...


@overload
def order(__override: Mapping[Any, Ordering]) -> Callable[[Cls], Cls]:
    ...


def order(__arg=None, *, before=None, after=None):
    if len([arg for arg in (__arg, before, after) if arg is not None]) != 1:
        stop_signature_abuse()
    if isinstance(__arg, Sequence):
        __arg = {field: order(after=prev) for field, prev in zip(__arg[1:], __arg)}
    if isinstance(__arg, Mapping):
        if not all(isinstance(val, Ordering) for val in __arg.values()):
            stop_signature_abuse()

        def decorator(cls: Cls) -> Cls:
            _order_overriding[cls] = __arg
            return cls

        return decorator
    elif __arg is not None and not isinstance(__arg, int):
        stop_signature_abuse()
    else:
        return Ordering(__arg, after, before)


def get_order_overriding(cls: type) -> Mapping[str, Ordering]:
    from apischema.objects.fields import get_field_name

    return {
        get_field_name(field, methods=True): ordering
        for sub_cls in reversed(cls.__mro__)
        if sub_cls in _order_overriding
        for field, ordering in _order_overriding[sub_cls].items()
    }


T = TypeVar("T")


def sort_by_order(
    cls: type,
    elts: Collection[T],
    name: Callable[[T], str],
    order: Callable[[T], Optional[Ordering]],
) -> Sequence[T]:
    from apischema.objects.fields import get_field_name

    order_overriding = get_order_overriding(cls)
    groups: Dict[int, List[T]] = defaultdict(list)
    after: Dict[str, List[T]] = defaultdict(list)
    before: Dict[str, List[T]] = defaultdict(list)
    for elt in elts:
        ordering = order_overriding.get(name(elt), order(elt))
        if ordering is None:
            groups[0].append(elt)
        elif ordering.order is not None:
            groups[ordering.order].append(elt)
        elif ordering.after is not None:
            after[get_field_name(ordering.after, methods=True)].append(elt)
        elif ordering.before is not None:
            before[get_field_name(ordering.before, methods=True)].append(elt)
        else:
            raise NotImplementedError
    if not after and not before and len(groups) == 1:
        return next(iter(groups.values()))
    result = []

    def add_to_result(elt: T):
        elt_name = name(elt)
        for before_elt in before[elt_name]:
            add_to_result(before_elt)
        result.append(elt)
        for after_elt in after[elt_name]:
            add_to_result(after_elt)

    for value in sorted(groups):
        for elt in groups[value]:
            add_to_result(elt)
    return result
