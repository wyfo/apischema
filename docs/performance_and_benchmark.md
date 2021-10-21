# Performance and benchmark

*apischema* is [faster](#benchmark) than its known alternatives, thanks to advanced optimizations.    

## Precomputed (de)serialization methods

*apischema* precomputes (de)serialization methods depending on the (de)serialized type (and other parameters); type annotations processing is done in the precomputation. Methods are then cached using `functools.lru_cache`, so `deserialize` and `serialize` don't recompute them every time.

!!! note
    The cache is automatically reset when global settings are modified, because it impacts the generated methods.

However, if `lru_cache` is fast, using the methods directly is faster, so *apischema* provides `apischema.deserialization_method` and `apischema.serialization_method`. These functions share the same parameters than `deserialize`/`serialize`, except the data/object parameter to (de)serialize. Using the computed methods directly can increase performances by 10%.

```python
{!de_serialization_methods.py!}
```

!!! warning
    Methods computed before settings modification will not be updated and use the old settings. Be careful to set your settings first.

## Serialization passthrough

!!! warning
    This feature has been released on a provisional basis. It has also been partially rolled back (it was initially covering dataclasses) to simplify the code for the next version; in fact the feature will then maybe not be as much useful, as *apischema* performance will normally be improved significantly enough to offer its own JSON dump implementation.

JSON serialization libraries expect primitive data types (`dict`/`list`/`str`/etc.). A non-negligible part of objects to be serialized are primitive.

When [type checking](#type-checking) is disabled (this is default), objects annotated with primitive types doesn't need to be transformed or checked; *apischema* can simply "pass through" them, and it will result into an identity serialization method.

Container types like `list` or `dict` are passed through only when the contained types are passed through too.

```python
{!pass_through_primitives.py!}
```

!!! note
    `Enum` subclasses which also inherit `str`/`int` are also passed through

### Passthrough options

Some JSON serialization libraries natively support types like `UUID` or `datetime`, sometimes with a faster implementation than the *apischema* one — [orjson](https://github.com/ijl/orjson), written in Rust, is a good example.

To take advantage of that, *apischema* provides `apischema.PassThroughOptions` class to specify which type should be passed through, whether they are supported natively by JSON libraries (or handled in a `default` fallback). 

`apischema.serialization_default` can be used as `default` fallback in combination to `PassThroughOptions`. It has to be instantiated with the same kwargs parameters (`aliaser`, etc.) than `serialization_method`.

```python
{!pass_through.py!}
```

!!! important
    Passthrough optimization always requires `check_type` to be `False`, in parameters or settings.

`PassThroughOptions` has the following parameters:

#### `any` — pass through `Any`

#### `collections` — pass through collections

Standard collections `list`, `tuple` and `dict` are natively handled by JSON libraries, but `set`, for example, isn't. Moreover, standard abstract collections like `Collection` or `Mapping`, which are used a lot, are
not guaranteed to have their runtime type supported (having a `set` annotated with
`Collection` for instance). 

But, most of the time, collections runtime types are `list`/`dict`, so others can be handled in `default` fallback.

!!! note
    Set-like type will not be passed through.

#### `enums` — pass through enums

#### `types` — pass through arbitrary types

Either a collection of types, or a predicate to determine if type has to be passed through.

### Passing through is not always faster

*apischema* is quite optimized and can perform better than using `default` fallback, as shown in the following example:

```python
{!vs_default.py!}
```
That's why passthrough optimization should be used wisely.

## Benchmark 

!!! note
    Benchmark presented is just [*Pydantic* benchmark](https://github.com/samuelcolvin/pydantic/tree/master/benchmarks) where *apischema* has been ["inserted"](https://github.com/wyfo/pydantic/tree/benchmark_apischema).

Below are the results of crude benchmark comparing *apischema* to *pydantic* and other validation libraries.

Package | Version | Relative Performance | Mean deserialization time
--- | --- | --- | ---
apischema | `0.16.0` |  | 40.2μs
pydantic | `1.8.2` | 1.9x slower | 77.8μs
attrs + cattrs | `21.2.0` | 2.0x slower | 79.7μs
valideer | `0.4.2` | 2.6x slower | 105.0μs
marshmallow | `3.14.0` | 5.2x slower | 210.5μs
voluptuous | `0.12.2` | 5.9x slower | 238.4μs
trafaret | `2.1.0` | 6.3x slower | 253.0μs
schematics | `2.1.1` | 19.3x slower | 775.4μs
django-rest-framework | `3.12.4` | 23.4x slower | 939.7μs
cerberus | `1.3.4` | 42.8x slower | 1717.6μs

Package | Version | Relative Performance | Mean serialization time
--- | --- | --- | ---
apischema | `0.15.3` |  | 18.0μs
pydantic | `1.8.2` | 2.9x slower | 51.3μs

Benchmarks were run with Python 3.9 (*CPython*) and the package versions listed above installed via *pypi* on *macOs* 11.2

!!! note
    A few precisions have to be written about these results:
    
    - *pydantic* benchmark is biased by the implementation of `datetime` parsing for *cattrs* (see [this post](https://stefan.sofa-rockers.org/2020/05/29/attrs-dataclasses-pydantic/) about it); in fact, if *cattrs* use a decently fast implementation, like the standard `datetime.fromisoformat`, *cattrs* becomes 3 times faster than *pydantic*, even faster than *apischema*. That being said, *apischema* is still claimed to be the fastest validation library of this benchmark because *cattrs* is not considered as a true validation library, essentially because of its *fail-fast* behavior. It's nevertheless a good (and fast) library, and its great performance has push *apischema* into optimizing its own performance a lot. 
    - *pydantic* benchmark mixes valid with invalid data (around 50/50), which doesn't correspond to real case. It means that error handling is very (too much?) important in this benchmark, and libraries like *cattrs* which raise and end simply at the first error encountered have a big advantage. Using only valid data, *apischema* becomes even faster than *cattrs*.
    
    
## FAQ

#### Why not ask directly for integration to *pydantic* benchmark?
[Done, but rejected](https://github.com/samuelcolvin/pydantic/pull/1525#issuecomment-630422702) because "apischema doesn't have enough usage". Let's change that!

