# Overview

## apischema

Makes your life easier when it comes to python API.

JSON (de)serialization, *GraphQL* and JSON schema generation through python typing, with a spoonful of sugar.

## Install
```shell
pip install apischema
```
It requires only Python 3.6+ (and dataclasses [official backport](https://pypi.org/project/dataclasses/) for version 3.6 only)

*PyPy3* is fully supported.

## Why another library?

This library fulfills the following goals:

- stay as close as possible to the standard library (dataclasses, typing, etc.) — as a consequence do not need plugins for editors/linters/etc.;
- be adaptable, provide tools to support any types (ORM, etc.);
- avoid dynamic things like using string for attribute name;
- support *GraphQL*;
- (*bonus*) be faster than alternatives.

No known alternative achieves all of this. 

!!! note
    Actually, *apischema* is even adaptable enough to enable support of competitor libraries in a few dozens of line of code ([pydantic support example](examples/pydantic_support.md) using [conversions feature](conversions.md))  

## Example

```python
{!quickstart.py!}
```
*apischema* works out of the box with you data model.

!!! note
    This example and further ones are using pytest stuff because they are in fact run as tests in the library CI
    
## *GraphQL*

*GraphQL* integration is detailed [further in the documentation](graphql/overview.md).

## FAQ

#### What is the difference between *apischema* and *pydantic*?

See the [dedicated section](difference_with_pydantic.md), there is a lot of difference. 

#### I already have my data model with my *SQLAlchemy*/ORM tables, will I have to duplicate my code, making one dataclass by table?
Why would you have to duplicate them? *apischema* can "work with user own types as well as foreign libraries ones". Some teasing of [conversion](conversions.md) feature: you can add default serialization for all your tables, or register different serializer that you can select according to your API endpoint, or both.

#### I need more accurate validation than "ensure this is an integer and not a string ", can I do that?
See the [validation](validation.md) section. You can use standard JSON schema validation (`maxItems`, `pattern`, etc.) that will be embedded in your schema or add custom Python validators for each class/fields/`NewType` you want.

*Let's start the apischema tour.*