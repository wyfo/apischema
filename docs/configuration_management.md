# Configuration management

*Apischema* is a multi-purpose deserialization library. If it's main use should be in API endpoint, that doesn't prevent to use it somewhere else, to parse application configuration for instance.

For JSON/YAML configurations, there is no need to develop further the use of library.

But there is many more ways of storing configurations, with environment variables or key-value store for example. When configurations are simple, there could be no need for a library like *Apischema*. However when it comes to being larger with some structure, it can play its cards right. 

## Dot-seraparated key-value

A common way of storing complex nested structures into flat key-value stores is to use dot-separated keys. 

*Apischema* provides an utility function to unflat this kind of data into nested JSON-like data, which can then be deserialized.

```python
{!configuration.py!}
```

