from datetime import datetime, timedelta

from apischema import deserialize

start, end = datetime.now(), datetime.now() + timedelta(1)
assert deserialize(
    tuple[datetime, datetime], [start, end], pass_through={datetime}
) == (start, end)
# Passing through types can also be deserialized normally from JSON types
assert deserialize(
    tuple[datetime, datetime],
    [start.isoformat(), end.isoformat()],
    pass_through={datetime},
) == (start, end)
