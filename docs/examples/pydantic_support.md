# Pydantic support

It takes only 30 lines of code to support `pydantic.BaseModel` and all of its subclasses. You could add these lines to your project using *pydantic* and start to benefit from *apischema* features.

This example deliberately doesn't use `set_object_fields` but instead the [conversions feature](../conversions.md) in order to roughly include *pydantic* "as is": it will reuse *pydantic* coercion, error messages, JSON schema, etc. This makes a full retro-compatible support.

As a result, lot of *apischema* features like GraphQL schema generation or `NewType` validation cannot be supported using this method — but they could be by using `set_object_fields` instead. 

```python
{!examples/pydantic_support.py!}
```