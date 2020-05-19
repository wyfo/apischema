from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Iterable, List, Set

from pytest import raises

from apischema import (ValidationError, build_input_schema,
                       field_input_converter, field_output_converter, from_data,
                       to_data, with_fields_set)


def branches_dict_from_list(branches: List[Tree]
                            ) -> Generator[Any, Any, Dict[str, Tree]]:
    nodes: Set[str] = set()
    for i, tree in enumerate(branches):
        nodes2 = set(tree.all_nodes)
        if nodes & nodes2:
            yield i, "duplicate nodes"
        nodes |= nodes2
    return {b.node: b for b in branches}


# Roughly equivalent to branch_dict_from_list
def branches_dict_from_list2(branches: List[Tree]) -> Dict[str, Tree]:
    nodes: Set[str] = set()
    errors: Dict[str, ValidationError] = {}
    for i, tree in enumerate(branches):
        nodes2 = set(tree.all_nodes)
        if nodes & nodes2:
            errors[str(i)] = ValidationError(["duplicate nodes"])
        nodes |= nodes2
    if errors:
        raise ValidationError(children=errors)
    return {b.node: b for b in branches}


def branches_dict_to_list(branches: Dict[str, Tree]) -> List[Tree]:
    return list(branches.values())


@with_fields_set
@dataclass
class Tree:
    node: str
    branches: Dict[str, Tree] = field(default_factory=dict, metadata=(
            field_input_converter(branches_dict_from_list) |
            field_output_converter(branches_dict_to_list)
    ))

    @property
    def all_nodes(self) -> Iterable[str]:
        yield self.node
        for tree in self.branches.values():
            yield tree.node
            yield from tree.all_nodes


def test_tree():
    data = {
        "node":     "root",
        "branches": [
            {"node": "leaf1"},
            {
                "node":     "node1",
                "branches": [
                    {"node": "leaf2"},
                    {"node": "leaf3"}
                ]
            }
        ]
    }
    tree = from_data(Tree, data)
    assert tree == Tree("root", {
        "leaf1": Tree("leaf1"),
        "node1": Tree("node1", {
            "leaf2": Tree("leaf2"),
            "leaf3": Tree("leaf3"),
        }),
    })
    assert to_data(tree) == data

    def ref_factory(cls: type) -> str:
        return f"#/definitions/{cls.__name__}"

    with raises(TypeError):
        build_input_schema(Tree)
    assert to_data(build_input_schema(Tree, ref_factory=ref_factory)) == {
        "additionalProperties": False,
        "properties":           {
            "node":     {"type": "string"},
            "branches": {
                "items":   {"$ref": "#/definitions/Tree"},
                "type":    "array"
            }
        },
        "required":             ["node"],
        "type":                 "object"
    }


def test_bad_tree():
    data = {
        "node":     "root",
        "branches": [
            {"node": "leaf1"},
            {
                "node":     "node1",
                "branches": [
                    {"node": "leaf2"},
                    {
                        "node":     "node2",
                        "branches": [{"node": "leaf2"}]
                    }
                ]
            }
        ]
    }
    with raises(ValidationError) as err:
        from_data(Tree, data)
    assert err.value == ValidationError(children={
        "branches": ValidationError(children={
            "1": ValidationError(children={
                "branches": ValidationError(children={
                    "1": ValidationError(["duplicate nodes"])
                })
            })
        })
    })
