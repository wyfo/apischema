from collections import defaultdict
from dataclasses import Field
from itertools import chain
from typing import AbstractSet, Any, Collection, Mapping, Set, overload

from apischema.metadata.keys import SKIP_METADATA, is_aggregate_field


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
                raise TypeError("Cannot use skipped field has dependency")
        self.fields: Mapping[Field, Collection[Field]] = fields
        self.groups: Collection[Collection[Field]] = groups

    def required_by(self) -> Mapping[Field, AbstractSet[Field]]:
        result: Mapping[Field, Set[Field]] = defaultdict(set)
        for group in self.groups:
            group = set(group)
            for field in group:
                result[field].update(group - {field})
        for field, required in self.fields.items():
            for req in required:
                result[req].add(field)
        return result
