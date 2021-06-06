# Class as union of its subclasses 

*Inspired by [https://github.com/samuelcolvin/pydantic/issues/2036](https://github.com/samuelcolvin/pydantic/issues/2036)*

A class can easily be deserialized as a union of its subclasses using deserializers. Indeed, when more than one deserializer are registered, it results in a union.

```python
{!examples/subclass_union.py!}
```