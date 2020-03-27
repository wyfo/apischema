import ast
from inspect import getsourcelines, isfunction
from itertools import takewhile
from typing import Callable, ClassVar, Dict, Mapping, Set, Type, get_type_hints


def getsource(func: Callable) -> str:
    lines, _ = getsourcelines(func)
    indentation = sum(1 for _ in takewhile(str.isspace, lines[0]))
    return "".join(line[indentation:] for line in lines)


Dependency = str
Dependencies = Set[Dependency]


class DependencyFinder(ast.NodeVisitor):
    def __init__(self):
        self.dependencies: Set[str] = set()

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            self.dependencies.add(node.attr)


def find_dependencies(method: Callable) -> Dependencies:
    finder = DependencyFinder()
    try:
        finder.visit(ast.parse(getsource(method)))
    except TypeError:
        return set()
    return finder.dependencies


cache: Dict[Callable, Dependencies] = {}


def is_class_var(dep: str, cls: Type, type_hints: Mapping[str, Type]) -> bool:
    # Cannot use is_dataclass because dependencies of dataclass are evaluated
    # before the dataclass decorator
    if not hasattr(cls, dep):
        return False
    if dep in type_hints:
        return getattr(type_hints[dep], "__origin__",
                       type_hints[dep]) is ClassVar
    return True


def find_end_dependencies(cls: type, method: Callable, rec_gard=()
                          ) -> Dependencies:
    if method not in cache:
        type_hints = get_type_hints(cls)
        dependencies = find_dependencies(method)
        class_vars = {dep for dep in dependencies
                      if is_class_var(dep, cls, type_hints)}
        dependencies -= class_vars
        for field in class_vars:
            attr = getattr(cls, field)
            if isinstance(attr, property):
                attr = attr.fget
            if isfunction(attr):
                if attr in rec_gard:
                    continue
                rec_deps = find_end_dependencies(cls, attr, (*rec_gard, attr))
                dependencies.update(rec_deps)
        cache[method] = dependencies
    return cache[method]
