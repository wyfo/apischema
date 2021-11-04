from datetime import datetime, timedelta

from apischema import deserialize

start, end = datetime.now(), datetime.now() + timedelta(1)
assert deserialize(
    tuple[datetime, datetime], [start, end], allowed_types={datetime}
) == (start, end)
# allowed types can also be deserialized normally from JSON types
assert deserialize(
    tuple[datetime, datetime],
    [start.isoformat(), end.isoformat()],
    allowed_types={datetime},
) == (start, end)
