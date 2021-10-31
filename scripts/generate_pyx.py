#!/usr/bin/env python3
import collections.abc
import dataclasses
import importlib
import inspect
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from types import FunctionType
from typing import (
    AbstractSet,
    Any,
    Dict,
    Iterable,
    Mapping,
    Match,
    Optional,
    Sequence,
    TextIO,
    Tuple,
    get_type_hints,
)

try:
    from typing import Literal

    CythonDef = Literal["cdef", "cpdef", "cdef inline"]
except ImportError:
    CythonDef = str  # type: ignore


ROOT_DIR = Path(__file__).parent.parent
TYPE_FIELD = "_type"


def remove_prev_compilation(package: str):
    for ext in ["so", "pyd"]:
        for file in (ROOT_DIR / "apischema" / package).glob(f"**/*.{ext}"):
            file.unlink()


cython_types_mapping = {
    type: "type",
    bytes: "bytes",
    bytearray: "bytearray",
    bool: "bint",
    str: "str",
    tuple: "tuple",
    Tuple: "tuple",
    list: "list",
    int: "long",
    dict: "dict",
    Mapping: "dict",
    collections.abc.Mapping: "dict",
    set: "set",
    AbstractSet: "set",
    collections.abc.Set: "set",
}


def cython_type(tp: Any) -> str:
    return cython_types_mapping.get(getattr(tp, "__origin__", tp), "object")


def cython_signature(
    def_type: CythonDef, func: FunctionType, self_type: Optional[type] = None
) -> str:
    parameters = list(inspect.signature(func).parameters.values())
    assert all(p.default is inspect.Parameter.empty for p in parameters)
    types = get_type_hints(func)
    param_with_types = []
    prefix = ""
    if parameters[0].name == "self":
        if self_type is not None:
            types["self"] = self_type
            prefix = self_type.__name__ + "_"
        else:
            param_with_types.append("self")
            parameters.pop(0)
    for param in parameters:
        param_with_types.append(cython_type(types[param.name]) + " " + param.name)
    return f"{def_type} {prefix}{func.__name__}(" + ", ".join(param_with_types) + "):"


class IndentedFile:
    def __init__(self, file: TextIO):
        self.file = file
        self.indentation = ""

    def write(self, txt: str):
        self.file.write(txt)

    def writelines(self, lines: Iterable[str]):
        self.file.writelines(lines)

    def writeln(self, txt: str = ""):
        self.write((self.indentation + txt + "\n") if txt else "\n")

    @contextmanager
    def indent(self):
        self.indentation += 4 * " "
        yield
        self.indentation = self.indentation[:-4]

    @contextmanager
    def write_block(self, txt: str):
        self.writeln(txt)
        with self.indent():
            yield


def rec_subclasses(cls: type) -> Iterable[type]:
    for sub_cls in cls.__subclasses__():
        yield sub_cls
        yield from rec_subclasses(sub_cls)


def get_body(
    func: FunctionType,
    switches: Mapping[str, Tuple[type, FunctionType]],
    cls: Optional[type] = None,
) -> Iterable[str]:
    lines, _ = inspect.getsourcelines(func)
    line_iter = iter(lines)
    for line in line_iter:
        if line.rstrip().endswith(":"):
            break
    else:
        raise NotImplementedError
    for line in line_iter:
        if cls is not None:

            def replace_super(match: Match):
                assert cls is not None
                super_cls = cls.__bases__[0].__name__
                return f"{super_cls}_{match.group(1)}(<{super_cls}>self, "

            line = re.sub(r"super\(\).(\w+)\(", replace_super, line)
        names = "|".join(switches)

        def sub(match: Match):
            self, name = match.groups()
            cls, _ = switches[name]
            return f"{cls.__name__}_{name}({self}, "

        yield re.sub(rf"([\w\.]+)\.({names})\(", sub, line)


def get_fields(cls: type) -> Sequence[dataclasses.Field]:
    return dataclasses.fields(cls) if dataclasses.is_dataclass(cls) else ()


def generate(package: str):
    module = importlib.import_module(f"apischema.{package}.methods")
    classes = [
        cls
        for cls in module.__dict__.values()
        if isinstance(cls, type) and cls.__module__ == module.__name__
    ]
    for cls in classes:
        cython_types_mapping[cls] = cls.__name__
        cython_types_mapping[Optional[cls]] = cls.__name__
        if sys.version_info >= (3, 10):
            cython_types_mapping[cls | None] = cls.__name__
    subclass_type: Dict[type, int] = {}
    switches = {}
    with open(ROOT_DIR / "apischema" / package / "methods.pyx", "w") as pyx_file:
        pyx = IndentedFile(pyx_file)
        pyx.write("cimport cython\n")
        with open(ROOT_DIR / "apischema" / package / "methods.py") as methods_file:
            for line in methods_file:
                if (
                    line.startswith("from ")
                    or line.startswith("import ")
                    or line.startswith("    ")
                    or line.startswith(")")
                    or not line.strip()
                ):
                    pyx.write(line)
                else:
                    break
        for cls in classes:
            class_def = f"cdef class {cls.__name__}"
            if cls.__bases__ != (object,):
                bases = ", ".join(base.__name__ for base in cls.__bases__)
                class_def += f"({bases})"
            with pyx.write_block(class_def + ":"):
                pyx.writeln("pass")
                write_init = cls in subclass_type
                for field in get_fields(cls):
                    if field.name in cls.__dict__.get("__annotations__", ()):
                        write_init = True
                        pyx.writeln(
                            f"cdef readonly {cython_type(field.type)} {field.name}"
                        )
                pyx.writeln()
                if write_init:
                    init_fields = [
                        field.name for field in get_fields(cls) if field.init
                    ]
                    with pyx.write_block(
                        "def __init__(" + ", ".join(["self"] + init_fields) + "):"
                    ):
                        for name in init_fields:
                            pyx.writeln(f"self.{name} = {name}")
                        if hasattr(cls, "__post_init__"):
                            lines, _ = inspect.getsourcelines(cls.__post_init__)  # type: ignore
                            pyx.writelines(lines[1:])
                        if cls in subclass_type:
                            pyx.writeln(f"self.{TYPE_FIELD} = {subclass_type[cls]}")
                    pyx.writeln()
                if cls.__bases__ == (object,):
                    if cls.__subclasses__():
                        for i, sub_cls in enumerate(rec_subclasses(cls)):
                            subclass_type[sub_cls] = i
                        pyx.writeln(f"cdef int {TYPE_FIELD}")
                    for name, obj in cls.__dict__.items():
                        if isinstance(obj, FunctionType) and not name.startswith("_"):
                            assert name not in switches
                            switches[name] = (cls, obj)
                            with pyx.write_block(cython_signature("cpdef", obj)):
                                pyx.writeln("raise NotImplementedError")
                            pyx.writeln()
                else:
                    for name, obj in cls.__dict__.items():
                        if (
                            isinstance(obj, (FunctionType, staticmethod))
                            and name in switches
                        ):
                            _, base_method = switches[name]
                            with pyx.write_block(
                                cython_signature("cpdef", base_method)
                            ):
                                args = ", ".join(
                                    inspect.signature(base_method).parameters
                                )
                                pyx.writeln(f"return {cls.__name__}_{name}({args})")
                            pyx.writeln()

        for cls, method in switches.values():
            for i, sub_cls in enumerate(rec_subclasses(cls)):
                if method.__name__ in sub_cls.__dict__:
                    sub_method = sub_cls.__dict__[method.__name__]
                    if isinstance(sub_method, staticmethod):
                        with pyx.write_block(
                            cython_signature("cdef inline", method, sub_cls)
                        ):
                            _, param = inspect.signature(method).parameters
                            func = sub_method.__get__(None, object)
                            pyx.writeln(f"return {func.__name__}({param})")
                    else:
                        with pyx.write_block(
                            cython_signature("cdef inline", sub_method, sub_cls)
                        ):
                            pyx.writelines(get_body(sub_method, switches, sub_cls))
                    pyx.writeln()
        for cls, method in switches.values():
            with pyx.write_block(cython_signature("cdef", method, cls)):
                pyx.writeln(f"cdef int {TYPE_FIELD} = self.{TYPE_FIELD}")
                for i, sub_cls in enumerate(rec_subclasses(cls)):
                    if method.__name__ in sub_cls.__dict__:
                        if_ = "if" if i == 0 else "elif"
                        with pyx.write_block(f"{if_} {TYPE_FIELD} == {i}:"):
                            self, *params = inspect.signature(method).parameters
                            args = ", ".join([f"<{sub_cls.__name__}>{self}", *params])
                            pyx.writeln(
                                f"return {sub_cls.__name__}_{method.__name__}({args})"
                            )
            pyx.writeln()
        for obj in module.__dict__.values():
            if isinstance(obj, FunctionType) and obj.__module__ == module.__name__:
                pyx.writeln(cython_signature("cdef inline", obj))
                pyx.writelines(get_body(obj, switches))
                pyx.writeln()


packages = ["deserialization", "serialization"]


def clean():
    for package in packages:
        remove_prev_compilation(package)


def main():
    clean()  # remove all before generate, because .so would be imported otherwise
    sys.path.append(str(ROOT_DIR))
    for package in packages:
        generate(package)


if __name__ == "__main__":
    main()
