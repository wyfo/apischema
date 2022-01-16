#!/usr/bin/env python3
import pathlib
import re
import sys

PATH = pathlib.Path(__file__)
ROOT_DIR = PATH.parent.parent
ALL_REGEX = re.compile(r"__all__ = \[(.|\n)*?\]")
WORD_REGEX = re.compile(r"\"\w+\"")


def sort_all(match: re.Match) -> str:
    s = match.group()
    assert s.startswith("__all__ = [")
    words = sorted(WORD_REGEX.findall(s))
    if len("__all__ = []") + sum(map(len, words)) + 2 * (len(words) - 1) > 88:
        return "__all__ = [\n    " + ",\n    ".join(words) + ",\n]"
    else:
        return "__all__ = [" + ", ".join(words) + "]"


def main():
    for filename in sys.argv[1:]:
        path = ROOT_DIR / filename
        if path == PATH:
            continue
        text = path.read_text()
        new_text = ALL_REGEX.sub(sort_all, text)
        if new_text != text:
            path.write_text(new_text)


if __name__ == "__main__":
    main()
