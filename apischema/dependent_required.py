from collections import defaultdict
from dataclasses import Field
from itertools import chain
from typing import AbstractSet, Any, Collection, Mapping, Set, overload

from apischema.utils import PREFIX

DEPENDENT_REQUIRED_ATTR = f"{PREFIX}dependent_required"

Requirements = Mapping[Field, AbstractSet[Field]]


class DependentRequired:
    @overload
    def __init__(self, fields: Mapping[Any, Collection[Any]]):
        ...

    @overload
    def __init__(self, fields: Mapping[Any, Collection[Any]], *groups: Collection[Any]):
        ...

    @overload
    def __init__(self, *groups: Collection[Any]):
        ...

    def __init__(self, *groups: Collection[Any]):  # type: ignore
        from apischema.metadata.keys import (
            MERGED_METADATA,
            PROPERTIES_METADATA,
            SKIP_METADATA,
            is_aggregate_field,
        )

        if not groups:
            return
        fields: Mapping[Any, Collection[Any]] = {}
        if isinstance(groups[0], Mapping):
            fields, *groups = groups  # type: ignore
        for field in chain(*groups, fields, chain.from_iterable(fields.values())):
            if not isinstance(field, Field):
                raise TypeError("Dependency must be a field")
            if is_aggregate_field(field):
                raise TypeError("Dependency cannot be a aggregate field")
            if SKIP_METADATA in field.metadata:
                raise TypeError("Cannot use skipped field as dependency")
            if (
                MERGED_METADATA in field.metadata
                or PROPERTIES_METADATA in field.metadata
            ):
                raise TypeError("Cannot use aggregate field as dependency")
        self.fields: Mapping[Field, Collection[Field]] = fields
        self.groups: Collection[Collection[Field]] = groups

    def __set_name__(self, owner, name):
        others = getattr(owner, DEPENDENT_REQUIRED_ATTR, ())
        setattr(owner, DEPENDENT_REQUIRED_ATTR, (*others, self))

    def _group_requirements(self) -> Mapping[Field, Set[Field]]:
        result: Mapping[Field, Set[Field]] = defaultdict(set)
        for group in self.groups:
            group = set(group)
            for field in group:
                result[field].update(group - {field})
        return result

    def required_by(self) -> Requirements:
        result = self._group_requirements()
        for field, required in self.fields.items():
            for req in required:
                result[req].add(field)
        return result

    def requiring(self) -> Requirements:
        result = self._group_requirements()
        for field, required in self.fields.items():
            for req in required:
                result[field].add(req)
        return result
