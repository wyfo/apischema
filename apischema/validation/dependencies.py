import ast
from inspect import getsourcelines, isfunction
from itertools import takewhile
from typing import AbstractSet, Callable, Collection, Dict, Set


def getsource(func: Callable) -> str:
    lines, _ = getsourcelines(func)
    indentation = sum(1 for _ in takewhile(str.isspace, lines[0]))
    return "".join(line[indentation:] for line in lines)


Dependency = str
Dependencies = AbstractSet[Dependency]


class DependencyFinder(ast.NodeVisitor):
    def __init__(self):
        self.dependencies: Set[str] = set()

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            self.dependencies.add(node.attr)

    # TODO Add warning in case of function call with self in parameter


def find_dependencies(method: Callable) -> Dependencies:
    finder = DependencyFinder()
    try:
        finder.visit(ast.parse(getsource(method)))
    except TypeError:
        return set()
    return finder.dependencies


cache: Dict[Callable, Dependencies] = {}


def find_all_dependencies(
    cls: type, method: Callable, rec_guard: Collection[str] = ()
) -> Dependencies:
    """Dependencies contains class variables (because they can be "fake" ones as in
       dataclasses)"""
    if method not in cache:
        dependencies = set(find_dependencies(method))
        for attr in list(dependencies):
            if not hasattr(cls, attr):
                continue
            member = getattr(cls, attr)
            if isinstance(member, property):
                member = member.fget
            if isfunction(member):
                dependencies.remove(attr)
                if member in rec_guard:
                    continue
                rec_deps = find_all_dependencies(cls, member, {*rec_guard, member})
                dependencies.update(rec_deps)
        cache[method] = dependencies
    return cache[method]
