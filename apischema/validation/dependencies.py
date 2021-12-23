import ast
import inspect
import textwrap
from typing import AbstractSet, Callable, Collection, Dict, Set

Dependencies = AbstractSet[str]


class DependencyFinder(ast.NodeVisitor):
    def __init__(self, param: str):
        self.param = param
        self.dependencies: Set[str] = set()

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == self.param:
            self.dependencies.add(node.attr)

    # TODO Add warning in case of function call with self in parameter
    # or better, follow the call, but it would be too hard (local import, etc.)


def first_parameter(func: Callable) -> str:
    try:
        return next(iter(inspect.signature(func).parameters))
    except StopIteration:
        raise TypeError("Cannot compute dependencies if no parameter")


def find_dependencies(func: Callable) -> Dependencies:
    try:
        finder = DependencyFinder(first_parameter(func))
        finder.visit(ast.parse(textwrap.dedent(inspect.getsource(func))))
    except ValueError:
        return set()
    return finder.dependencies


cache: Dict[Callable, Dependencies] = {}


def find_all_dependencies(
    cls: type, func: Callable, rec_guard: Collection[str] = ()
) -> Dependencies:
    """Dependencies contains class variables (because they can be "fake" ones as in
    dataclasses)"""
    if func not in cache:
        dependencies = set(find_dependencies(func))
        for attr in list(dependencies):
            if not hasattr(cls, attr):
                continue
            member = getattr(cls, attr)
            if isinstance(member, property):
                member = member.fget
            if callable(member):
                dependencies.remove(attr)
                if member in rec_guard:
                    continue
                rec_deps = find_all_dependencies(cls, member, {*rec_guard, member})
                dependencies.update(rec_deps)
        cache[func] = dependencies
    return cache[func]
