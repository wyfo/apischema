# Overview

## apischema

JSON (de)serialization, GraphQL and JSON schema generation using Python typing.

*apischema* makes your life easier when dealing with API data.

<!--
## Documentation

[https://wyfo.github.io/apischema/](https://wyfo.github.io/apischema/)
-->

## Install
```shell
pip install apischema
```
It requires only Python 3.6+ (and dataclasses [official backport](https://pypi.org/project/dataclasses/) for version 3.6 only)

*PyPy3* is fully supported.

## Why another library?

<!--
(If you wonder how this differs from the *pydantic* library, see the [dedicated section of the documentation(difference_with_pydantic.md) — there are many differences.)
-->

This library fulfills the following goals:

- stay as close as possible to the standard library (dataclasses, typing, etc.) — as a consequence we do not need plugins for editors/linters/etc.;
- avoid object-oriented limitations — do not require a base class — thus handle easily every type (`Foo`, `list[Bar]`, `NewType(Id, int)`, etc.) the same way.
- be adaptable, provide tools to support any types (ORM, etc.);
- avoid dynamic things like using raw strings for attributes name - play nicely with your IDE.

No known alternative achieves all of this, and apischema is also [(a lot) faster](optimizations_and_benchmark.md#benchmark) than all of them.

On top of that, because APIs are not only JSON, *apischema* is also a complete GraphQL library

<!--
![benchmark chart](benchmark_chart_light.svg#gh-light-mode-only)
![benchmark chart](benchmark_chart_dark.svg#gh-dark-mode-only)
-->

!!! note
    Actually, *apischema* is even adaptable enough to enable support of competitor libraries in a few dozens of line of code ([pydantic support example](examples/pydantic_support.md) using [conversions feature](conversions.md))

## Example

```python
{!quickstart.py!}
```
*apischema* works out of the box with your data model.

!!! note
    This example and further ones are using *pytest* API because they are in fact run as tests in the library CI

### Run the documentation examples

All documentation examples are written using the last Python minor version — currently 3.10 — in order to provide up-to-date documentation. Because Python 3.10 specificities (like [PEP 585](https://www.python.org/dev/peps/pep-0604/)) are used, this version is "mandatory" to execute the examples as-is.

In addition to *pytest*, some examples use third-party libraries like *SQLAlchemy* or *attrs*. All of this dependencies can be downloaded using the `examples` extra with
```shell
pip install apischema[examples]
```

Once dependencies are installed, you can simply copy-paste examples and execute them, using the proper Python version. 

## FAQ

#### What is the difference between *apischema* and *pydantic*?

See the [dedicated section](difference_with_pydantic.md) — there are many differences.

#### I already have my data model with my *SQLAlchemy*/ORM tables, will I have to duplicate my code, making one dataclass per table?
No, `apischema` works with user-defined types as well as types from foreign libraries. Using the [conversion](conversions.md) feature, you can add default serialization for all your tables, or register a different serializer that you can select according to your API endpoint, or both.

#### I need more accurate validation than "ensure this is an integer and not a string ", can I do that?
See the [validation](validation.md) section. You can use standard JSON schema validation (`maxItems`, `pattern`, etc.) that will be embedded in your schema or add custom Python validators for each class/fields/`NewType` you want.