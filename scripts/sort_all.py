#!/usr/bin/env python3
import os
from pathlib import Path
from subprocess import run

PACKAGE_DIR = Path(__file__).parent.parent / "apischema"

for root, dirs, files in os.walk(PACKAGE_DIR):
    for filename in files:
        if not filename.endswith(".py"):
            continue
        path = f"{root}/{filename}"
        with open(path) as f:
            lines = f.readlines()
        try:
            all_first_line = next(i for i, l in enumerate(lines) if "__all__ = [" in l)
        except StopIteration:
            continue
        all_last_line = next(
            i + all_first_line for i, l in enumerate(lines[all_first_line:]) if "]" in l
        )
        namespace: dict = {}
        exec("".join(lines[all_first_line : all_last_line + 1]), namespace)
        if namespace["__all__"] == sorted(namespace["__all__"]):
            continue
        __all__ = ", ".join(f'"{s}"' for s in sorted(namespace["__all__"]))
        with open(path, "w") as f:
            f.writelines(lines[:all_first_line])
            f.write(f"__all__ = [{__all__}]\n")
            f.writelines(lines[all_last_line + 1 :])
        run(["black", path])
