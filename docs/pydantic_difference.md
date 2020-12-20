# Difference with pydantic

As the question is often asked, it is answered in a dedicated section. Here are some the key differences between *Apischema* and *pydantic*:

### *Apischema* is faster

*pydantic* uses Cython to improve its performance; *Apischema* doesn't need it and is still 1.5x faster according to [*pydantic* benchmark](benchmark.md) — more than 2x when *pydantic* is not compiled with Cython.

Better performance, but not at the cost of fewer functionalities; that's rather the opposite: [dynamic aliasing](json_schema.md#dynamic-aliasing-and-default-aliaser), [conversions](conversions.md), [merged fields](data_model.md#composition-over-inheritance---composed-dataclasses-merging), etc.

### *Apischema* can generate [*GraphQL* schema](graphql/overview.md) from your resolvers

Not just a simple printable schema but a complete `graphql.GraphQLSchema` which can be used to execute your queries/mutations/subscriptions through your resolvers/subscribers, powered by *Apischema* (de)serialization and conversions features.

Types and resolvers can be used both in traditional JSON-oriented API and GraphQL API

### *Apischema* uses standard dataclasses and types

*pydantic* uses its own `BaseModel` class, or its own pseudo-`dataclass`, so you are forced to tie all your code to the library, and you cannot easily reuse code written in a more standard way or in external libraries.

By the way, Pydantic use expressions in typing annotations (`conint`, etc.), while it's not recommended and treated as an error by tools like *Mypy*

### *Apischema* doesn't require external plugins for editors, linters, etc.

*pydantic* requires a plugin to allow *Mypy* to type checked `BaseModel` and others *pydantic* singularities (and to not raise errors on it); plugin are also needed for editors.

### *Apischema* doesn't mix up (de)serialization with your code

While *pydantic* mix up model constructor with deserializer, *Apischema* use dedicated functions for its features, meaning your dataclasses are instantiated normally with type checking. In your code, you manipulate objects; (de)serialization is for input/output.

*Apischema* also doesn't mix up validation of external data with your statically checked code; there is no runtime validation in constructors.

### *Apischema* truly works out-of-the-box with forward type references (especially for recursive model)

*pydantic* requires calling `update_forward_refs` method on recursive types, while *Apischema* "just works".

### *Apischema* supports `Generic` in Python 3.6 and without requiring additional stuff

*pydantic* `BaseModel` cannot be used with generic model, you have to use `GenericModel`, and it's not supported in Python 3.6.

With *Apischema*, you just write your generic classes normally. 

### *Apischema* [conversions](conversions.md) feature allows to support any type defined in your code, but also in external libraries

*pydantic* doesn't make it easy to support external types, like `bson.ObjectId`; see this [issue](https://github.com/tiangolo/fastapi/issues/68) on the subject. You could dynamically add a `__get_validators__` method to foreign classes, but that doesn't work with builtin types like `collection.deque` and other types written in C. 

Serialization customization is harder, with definition of encoding function by model; it cannot be done at the same place as deserialization. There is also no correlation done between (de)serialization customization and model JSON schema; you could have to overwrite the generated schema if you don't want to get an inconsistency.

*Apischema* only requires a few lines of code to support any type you want, from `bson.ObjectId` to *SQLAlchemy* models by way of builtin and generic like `collection.deque`, and even [*pydantic*](#apischema-supports-pydantic). Conversions are also integrated in JSON schema this one is generated according to the source/target of the conversion

Here is a comparison of a custom type support:

```python
import re
from typing import NamedTuple, NewType

import apischema
import pydantic.validators

# Serialization can only be customized into the enclosing models
class RGB(NamedTuple):
    red: int
    green: int
    blue: int

    # If you don't put this method, RGB schema will be: 
    # {'title': 'Rgb', 'type': 'array', 'items': {}}
    @classmethod
    def __modify_schema__(cls, field_schema) -> None:
        field_schema.update({"type": "string", "pattern": r"#[0-9A-Fa-f]{6}"})
        field_schema.pop("items", ...)

    @classmethod
    def __get_validators__(cls):
        yield pydantic.validators.str_validator
        yield cls.validate

    @classmethod
    def validate(cls, value) -> 'RGB':
        if not isinstance(value, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None:
            raise ValueError("Invalid RGB")
        return RGB(red=int(value[1:3], 16), green=int(value[3:5], 16), blue=int(value[5:7], 16))
    
# Simpler with apischema

class RGB(NamedTuple):
    red: int
    green: int
    blue: int
    
HexaRGB = NewType("HexaRGB", str)
# pattern is used in JSON schema and in deserialization validation
apischema.schema(pattern=r"#[0-9A-Fa-f]{6}")(HexaRGB)

@apischema.deserializer
def from_hexa(hexa: HexaRGB) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))

@apischema.serializer
def to_hexa(rgb: RGB) -> HexaRGB:
    return HexaRGB(f"#{rgb.red:02x}{rgb.green:02x}{rgb.blue:02x}")

assert (  # schema is inherited from deserialized type
    apischema.json_schema.deserialization_schema(RGB)
    == apischema.json_schema.deserialization_schema(HexaRGB)
    == {
        "$schema": "http://json-schema.org/draft/2019-09/schema#",
        "type": "string", 
        "pattern": "#[0-9A-Fa-f]{6}",
    }
)
```

### *Apischema* allows you to use composition over inheritance

[Merged fields](data_model.md#composition-over-inheritance---composed-dataclasses-merging) is a distinctive *Apischema* feature that is very handy to build complex model from smaller fragments; you don't have to merge yourself the fields of your fragments in a complex class with a lot of fields, *Apischema* deal with it for you, and your code is kept simple.

### *Apischema* has a functional approach, *pydantic* has an object one

*pydantic* features are based on `BaseModel` methods. You have to have a `BaseModel` instance to do anything, even if you manipulate only an integer. Complex *pydantic* stuff like `__root__` model or deserialization customization come from this approach.

*Apischema* is functional, it doesn't use method but simple functions, which works with all types. You can also register conversions for any types similarly you would implement a type class in a functional language. And your class namespace don't mix up with a mandatory base class' one.

### *Apischema* can use both *camelCase* and *snake_case* with the same types

While *pydantic* field aliases are fixed at model creation, *Apischema* [let you choose](json_schema.md#dynamic-aliasing-and-default-aliaser) which aliasing you want at (de)serialization time. 

It can be convenient if you need to juggle with cases for the same models between frontends and other backend services for example.

### *Apischema* doesn't coerce by default

Your API respects its schema. 

It can also coerce, for example to parse configuration file, and coercion can be adjusted (for example coercing list from comma-separated string). 

### *Apischema* has a better integration of JSON schema/*OpenAPI*

With *pydantic*, if you want to have a `nullable` field in the generated schema, you have to put `nullable` into schema extra keywords.

*Apischema* is bound to the last JSON schema version but offers conversion to other version like *OpenAPI* 3.0 and `nullable` is added for `Optional` types.

*Apischema* also support more advanced features like `dependentRequired` or `unevaluatedProperties`. Reference handling is also more [flexible](json_schema.md#complexrecursive-types---json-schema-definitionsopenapi-components)

### *Apischema* can add JSON schema to `NewType`

So it will be used in deserialization validation. You can use `NewType` everywhere, to gain a better type checking, self-documented code.

### *Apischema* validators are regular methods with [automatic dependencies management](validation.md#automatic-dependency-management)

Using regular methods allows benefiting of type checking of fields, where *pydantic* validators use dynamic stuffs and are not type-checked or have to get redundant type annotations.

*Apischema* validators also have automatic dependency management. And *Apischema* directly supports JSON schema [property dependencies](json_schema.md#property-dependencies).

Comparison is simple with an example:

```python
from dataclasses import dataclass

import apischema
import pydantic

class UserModel(pydantic.BaseModel):
    username: str
    password1: str
    password2: str

    @pydantic.root_validator
    def check_passwords_match(cls, values):
        # What is the type of of values? of values['password1']?
        # If you rename password1 field, validator will hardly be updated
        # You also have to test yourself that values are provided
        pw1, pw2 = values.get('password1'), values.get('password2')
        if pw1 is not None and pw2 is not None and pw1 != pw2:
            raise ValueError('passwords do not match')
        return values

    
@dataclass
class LoginForm:
    username: str
    password1: str
    password2: str

    @apischema.validator
    def check_password_match(self):
        # Typed checked, simpler, and not executed if error on password1 or password2
        if self.password1 != self.password2:
            raise ValueError('passwords do not match')
```

### *Apischema* supports *pydantic*

It's not a feature, is just the result of [20 lines of code](examples/pydantic_compatibility.md).
