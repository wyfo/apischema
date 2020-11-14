# Recoverable fields

*Inspired by [https://github.com/samuelcolvin/pydantic/issues/2036](https://github.com/samuelcolvin/pydantic/issues/2036)*

A class can easily be deserialized as an union of its subclasses using deserializers. Indeed, when more than one deserializer are registered, it results in an union.

```python
{!examples/subclasses_union.py!}
```