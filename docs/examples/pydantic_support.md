# Pydantic support

It takes only 20 lines of code to support `pydantic.BaseModel` and all of its subclasses. You could add these lines to your project using *pydantic* and start to benefit of *apischema* features.

!!! note
    This support unfortunately doesn't include *GraphQL* schema feature.

!!! note
    *pydantic* pseudo-dataclasses are de facto supported but without *pydantic* extra features; they could be fully supported, but it would require some additional lines of code.  

```python
{!examples/pydantic_support.py!}
```