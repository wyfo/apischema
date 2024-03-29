#!/usr/bin/env python3
import pathlib
import re
import sys

ROOT_DIR = pathlib.Path(__file__).parent.parent
README = ROOT_DIR / "README.md"
INDEX = ROOT_DIR / "docs" / "index.md"
QUICKSTART = ROOT_DIR / "examples" / "quickstart.py"

USED_FILES = {str(path.relative_to(ROOT_DIR)) for path in (INDEX, QUICKSTART)}


def main():
    content = INDEX.read_text()
    # Set title
    content = re.sub(r"# Overview\s*## apischema", "# apischema", content)
    # Remove FAQ
    content = content[: content.index("## FAQ")]
    # Remove admonitions
    content = re.sub(r"!!! note\n\s*(.*)\n", lambda m: f"> {m.group(1)}\n", content)
    # Add chart
    # TODO remove this unused part?
    content = content.replace(
        r"<!--insert chart-->",
        "\n".join(
            "![benchmark chart](https://wyfo.github.io/apischema/dev/"
            f"benchmark_chart_{theme}#gh-{theme}-mode-only)"
            for theme in ("light", "dark")
        ),
    )
    # Uncomment
    content = re.sub(r"<!--\n(\s*(.|\n)*?\s*)\n-->", lambda m: m.group(1), content)
    # TODO remove this unused part?
    content = re.sub(
        r"(\d+\.\d+)/benchmark_chart\.svg", "dev/benchmark_chart.svg", content
    )
    # Rewrite links
    content = re.sub(
        r"\(([\w/]+)\.(md|svg)(#[\w-]+)?\)",
        lambda m: f"(https://wyfo.github.io/apischema/dev/{m.group(1)}"
        + (".svg" if m.group(2) == "svg" else "")
        + (m.group(3) or "")
        + ")",
        content,
    )
    # Add quickstart
    content = re.sub(
        "```python(.|\n)*?```", f"```python\n{QUICKSTART.read_text()}```", content
    )
    README.write_text(content)


if __name__ == "__main__":
    if not set(sys.argv).isdisjoint(USED_FILES):
        main()
