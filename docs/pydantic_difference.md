# Difference with pydantic

The question is often asked, so it is answered in a dedicated section. Here are some the key differences between *Apischema* and *pydantic*

### *Apischema* is faster

*pydantic* uses Cython to improve its performance (with some side effects in its code); *Apischema* doesn't need it and is still 1.5x faster — more than 2x when *pydantic* is not compiled with Cython.

### *Apischema* can generate *GraphQL* schema from your resolvers

And the same types can be used in JSON oriented API and GraphQL API.

### *Apischema* uses standard dataclasses and types

*pydantic* uses its own `BaseModel` class, or it's own pseudo-`dataclass`, so you are forced to tie all your code the library, and you cannot reuse code written in a more standard way.

By the way, Pydantic use expressions in typing annotations (`conint`, etc.), while it's not recommended and treated as an error by tools like *Mypy*

### *Apischema* doesn't require external plugins for editors, linters, etc.

*pydantic* requires a plugin to allow *Mypy* to type checked `BaseModel` and others *pydantic* singularities (and to not raise errors on it); plugin are also needed for editors.

*Apischema* for its part doesn't have borderline stuff like `conint` annotations and because it uses standard dataclasses, it doesn't need anything else that dataclass support, which is standard on editors and type checkers.

### *Apischema* truly works out-of-the-box with forward type references (especially for recursive model)

*pydantic* requires calling `update_forward_refs` method on recursive types, while *Apischema* "just works".

### *Apischema* doesn't mix up (de)serialization with your code

*pydantic* mix up model constructor with deserializer. That ruins the concept of type checking if you want to instantiate a model from your code.

*Apischema* use dedicated functions for its features, meaning your dataclasses are instanciated normally with type checking. In your code, you manipulate objects; (de)serialization is for input/output.

*Apischema* also doesn't mix up validation of external data with your statically checked code; there is no runtime validation in constructors.

### *Apischema* [conversions](conversions.md) feature allows to support any type defined in your code, but also in external libraries

*pydantic* is limited to the type you define in your own code (and to those it defines in its code); you cannot deserialize directly a `bson.ObjectID`. You are forced to use pseudo types to overload what you want and by using inheritance (see [issue on `bson.ObjectId`](https://github.com/tiangolo/fastapi/issues/68)).

!!! note
    In fact, you could dynamically add a method `__get_validators__` to `bson.ObjectID`, but that's not intuitive, and it doesn't work with builtin types like `collection.deque` and other types written in C.  

*Apischema* has no limit, and it only requires a few lines of code to support what you want, from `bson.ObjectId` to *SQLAlchemy* models by way of builtin and generic like `collection.deque`, and even [*pydantic*](#apischema-supports-pydantic). 

Here is a comparison of a custom type support:

```python
import re
from typing import NamedTuple

import apischema

# Serialization has to be handled in each class which has an RGB field
# or at each call of of json method
class RGB(NamedTuple):
    red: int
    green: int
    blue: int
    
    @classmethod
    def __modify_schema__(cls, field_schema) -> None:
        field_schema.update({"type": "string", "pattern": rgb_regex})
        field_schema.pop("items", ...)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> 'RGB':
        if re.fullmatch(r"#[0-9A-Fa-f]{6}, value) is None:
            raise ValueError("Invalid RGB")
        return RGB(red=int(value[1:3], 16), green=int(value[3:5], 16), blue=int(value[5:7], 16))
    
    
# Simplified with apischema

@apischema.schema(pattern=r"#[0-9A-Fa-f]{6})
class RGB(NamedTuple):
    red: int
    green: int
    blue: int

    
@apischema.serializer
def to_hexa(rgb: RGB) -> str:
    return f"#{rgb.red:02x}{rgb.green:02x}{rgb.blue:02x}"


@apischema.deserializer
def from_hexa(hexa: str) -> RGB:
    return RGB(int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16))
```

### *Apischema* has a functional approach, *pydantic* has an object one, with its limitations

Every functionality of *pydantic* is a method of `BaseModel`. You have to have a `BaseModel` instance to do something, even if you manipulate only an integer. So you have to use complex stuff like *root type*, and to have `BaseModel` namespace mixing up with your class namespace. 

Also, because Python has limited object features (no extensions like in Swift or Kotlin), you cannot use easily types you don't defined yourself.

*Apischema* is functional, it doesn't use method but simple functions, which works for every types. You can also register conversions for any types similarly you would implement a type class in a functional language (or adding an extension in Swift or Kotlin).

This approach has far fewer limitations. It also allows to add feature in to *Apischema* (in the library directly or in a plugin) more easily, without breaking the paradigm; in fact, third-party plugin cannot add methods to `BaseModel` (without breaking static checking), and if *pydantic* adds a method, you have to make sure it will not mangle your model namespace.

### *Apischema* allows you to use composition over inheritance

[Merged fields](data_model.md#composition-over-inheritance---composed-dataclasses-merging) is a distinctive *Apischema* feature that is very handy to build complexe model from smaller fragments; you don't have to merge yourself the fields of your fragments in a complex class with a lot of fields, *Apischema* deal with it for you, and your code is kept simple.

### *Apischema* supports `Generic` in Python 3.6 and without requiring additional stuff

*pydantic* `BaseModel` cannot be used with generic model, you have to use `GenericModel`, and it's not supported in Python 3.6.

With *Apischema*, you just write your generic classes normally. 

### *Apischema* doesn't coerce by default

Your API respects its schema. 

But it can also coerce, for example to parse configuration file, and coercion can be adjusted (for example coercing list from comma-separated string). 

### *Apischema* has a better integration of JSON schema/*OpenAPI*

With *pydantic*, if you want to have a `nullable` field in the generated schema, you have to put `nullable` into schema extra keywords.

*Apischema* is binded to the last JSON schema version but offers conversion to other version like *OpenAPI* 3.0 and `nullable` is added for `Optional` types.

*Apischema* also support more advanced features like `dependentRequired` or `unevaluatedProperties`. Reference handling is also more [flexible](json_schema.md#complexrecursive-types---json-schema-definitionsopenapi-components)

### *Apischema* can add JSON schema to `NewType`

And that's very convenient; you can use `NewType` everywhere, to gain a better type checking, a better self-documented code.

### *Apischema* validators are regular method with [automatic dependencies management](validation.md#automatic-dependencies-management)

Using regular methods allows to benefit of type checking of fields, where *pydantic* validators use dynamic stuffs and are not type-checked or have to add redundant type annotations.

*Apischema* validators also have automatic dependencies management. And *Apischema* directly supports JSON schema [property dependencies](json_schema.md#property-dependencies).

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
        # What is the type of of values? of values['password1']
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

