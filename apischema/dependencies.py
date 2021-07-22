from collections import defaultdict
from dataclasses import dataclass
from typing import (
    AbstractSet,
    Any,
    Collection,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Set,
    Tuple,
    overload,
)

from apischema.cache import CacheAwareDict
from apischema.objects.fields import check_field_or_name, get_field_name

_dependent_requireds: MutableMapping[
    type, List[Tuple[Any, Collection[Any]]]
] = CacheAwareDict(defaultdict(list))

DependentRequired = Mapping[str, AbstractSet[str]]


def get_dependent_required(cls: type) -> DependentRequired:
    result: Dict[str, Set[str]] = defaultdict(set)
    for sub_cls in cls.__mro__:
        for field, required in _dependent_requireds[sub_cls]:
            result[get_field_name(field)].update(map(get_field_name, required))
    return result


@dataclass
class DependentRequiredDescriptor:
    fields: Mapping[Any, Collection[Any]]
    groups: Collection[Collection[Any]]

    def __set_name__(self, owner, name):
        setattr(owner, name, None)
        dependent_required(self.fields, *self.groups, owner=owner)


@overload
def dependent_required(
    fields: Mapping[Any, Collection[Any]], *groups: Collection[Any], owner: type = None
):
    ...


@overload
def dependent_required(*groups: Collection[Any], owner: type = None):
    ...


def dependent_required(*groups: Collection[Any], owner: type = None):  # type: ignore
    if not groups:
        return
    fields: Mapping[Any, Collection[Any]] = {}
    if isinstance(groups[0], Mapping):
        fields, *groups = groups  # type: ignore
    if owner is None:
        return DependentRequiredDescriptor(fields, groups)
    else:

        dep_req = _dependent_requireds[owner]
        for field, required in fields.items():
            dep_req.append((field, required))
            check_field_or_name(field)
            for req in required:
                check_field_or_name(req)
        for group in map(list, groups):
            for i, field in enumerate(group):
                check_field_or_name(field)
                dep_req.append((field, [group[:i], group[i:]]))
