#!/usr/bin/env python3
import os
import re
import sys
from itertools import takewhile
from pathlib import Path
from shutil import rmtree
from typing import Iterator, Tuple

ROOT_DIR = Path(__file__).parent.parent

EXAMPLES_PATH = ROOT_DIR / "examples"
GENERATED_PATH = ROOT_DIR / "tests" / "__generated__"
with open(ROOT_DIR / "scripts" / "test_wrapper.py") as wrapper_file:
    before_lines = [*takewhile(lambda l: not l.startswith("##"), wrapper_file), "##\n"]
    after_lines = ["##\n", *wrapper_file]


def iter_paths() -> Iterator[Tuple[Path, Path]]:
    for example_path in EXAMPLES_PATH.glob("**/*.py"):
        if example_path.name == "__init__.py":
            continue
        relative_path = example_path.relative_to(EXAMPLES_PATH)
        test_dir = GENERATED_PATH / relative_path.parent
        test_dir.mkdir(parents=True, exist_ok=True)
        yield example_path, test_dir / f"test_{relative_path.name}"


INDENTATION = 4 * " "
union_regex = re.compile(r"..(\w+(\[.+?\])? \| )+(\w+)")
# regex is not recursive and thus cannot catch things like Connection[Ship | None] | None

try:
    from re import Match
except ImportError:
    Match = ...  # type: ignore


def replace_union(match: Match) -> str:
    args = list(map(str.strip, match.group(0)[2:].split("|")))
    if match.group(0)[0] == "=" and args[-1] != "None":  # graphql types
        return match.group(0)
    joined = ", ".join(args)
    return match.group(0)[:2] + f"Union[{joined}]"


def handle_union(line: str) -> str:
    return union_regex.sub(replace_union, line)


def main():
    if GENERATED_PATH.exists():
        rmtree(GENERATED_PATH)
    GENERATED_PATH.mkdir(parents=True)
    for example_path, test_path in iter_paths():
        with open(example_path) as example:
            with open(test_path, "w") as test:
                if (
                    sys.version_info < (3, 10)
                    or os.getenv("TOXENV", None) != "py310"
                    or True
                ):
                    example = map(handle_union, example)
                # 3.9 compatibility is added after __future__ import
                # However, Annotated/Literal/etc. can be an issue
                first_line = next(example)
                if first_line.startswith("from __future__ import"):
                    test.write(first_line)
                    test.writelines(before_lines)
                else:
                    test.writelines(before_lines)
                    test.write(first_line)
                test_count = 0
                while example:
                    # Classes must be declared in global namespace in order to get
                    # get_type_hints and is_method to work
                    # Test function begin at the first assertion.
                    for line in example:
                        if line.startswith("assert ") or line.startswith(
                            "with raises("
                        ):
                            test.write(f"def {test_path.stem}{test_count}():\n")
                            test.write(INDENTATION + line)
                            break
                        test.write(line)
                    else:
                        break
                    cur_indent = INDENTATION
                    for line in example:
                        if any(line.startswith(s) for s in ("class ", "@")):
                            test.write(line)
                            test_count += 1
                            break
                        test.write(cur_indent + line)
                        if '"""' in line:
                            cur_indent = "" if cur_indent else INDENTATION
                    else:
                        break
                test.writelines(after_lines)

    for path in GENERATED_PATH.glob("**"):
        if path.is_dir():
            open(path / "__init__.py", "w").close()


if __name__ == "__main__":
    main()
