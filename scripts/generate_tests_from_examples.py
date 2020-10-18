#!/usr/bin/env python3
import sys
from itertools import chain
from pathlib import Path
from shutil import rmtree
from typing import Iterator, Tuple

ROOT_DIR = Path(__file__).parent.parent

EXAMPLES_PATH = ROOT_DIR / "examples"
GENERATED_PATH = ROOT_DIR / "tests" / "__generated__"
with open(ROOT_DIR / "scripts" / "39_compatibility.py") as compat_file:
    compatibility_lines = ["##\n", *compat_file, "##\n"]


def iter_paths() -> Iterator[Tuple[Path, Path]]:
    for example_path in EXAMPLES_PATH.glob("**/*.py"):
        if example_path.name == "__init__.py":
            continue
        relative_path = example_path.relative_to(EXAMPLES_PATH)
        test_dir = GENERATED_PATH / relative_path.parent
        test_dir.mkdir(parents=True, exist_ok=True)
        yield example_path, test_dir / f"test_{relative_path.name}"


def generate():
    if GENERATED_PATH.exists():
        rmtree(GENERATED_PATH)
    GENERATED_PATH.mkdir(parents=True)
    for example_path, test_path in iter_paths():
        with open(example_path) as example:
            with open(test_path, "w") as test:
                # Test function cannot be put at the top of the file because:
                # - __future__ imports must be at top
                # - class must be declared in global namespace for get_type_hints
                for line in example:
                    # 3.9 compatibility is added at the end of import section
                    if line.strip() and not any(
                        line.startswith(pfx) for pfx in ("import", "from", "    ", ")")
                    ):
                        test.writelines(compatibility_lines)
                        test.write(line)
                        break
                    test.write(line)
                else:
                    raise NotImplementedError()
                for line in example:
                    # test function begin at the first test assertion
                    if line.startswith("assert ") or line.startswith("with raises("):
                        test.write(f"def {test_path.stem}():\n")
                        test.writelines(f"    {l}" for l in chain([line], example))
                        break
                    test.write(line)
    for path in GENERATED_PATH.glob("**"):
        if path.is_dir():
            open(path / "__init__.py", "w").close()


def retro_propagate():
    for example_path, test_path in iter_paths():
        if not test_path.exists():
            continue
        with open(test_path) as test:
            with open(example_path, "w") as example:
                for line in test:
                    if line.startswith("##"):
                        for l in test:
                            if l.startswith("##"):
                                break
                    if line.startswith("def test_"):
                        example.writelines(l[4:] for l in test)
                        break
                    example.write(line)


def main():
    retro_propagate() if "-r" in sys.argv else generate()


if __name__ == "__main__":
    main()