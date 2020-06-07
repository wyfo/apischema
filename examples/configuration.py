from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Collection

from apischema import deserialize
from apischema.deserialization import unflat_key_value

# Could be extracted from ini file, or environment variables with `os.environ`
configuration = [
    ("database.host", "191.132.67.45"),
    ("database.user", "guest"),
    ("filtered_subnets.0", "247.252.191.00/24"),
    ("filtered_subnets.1", "207.34.172.00/24"),
]


@dataclass
class Database:
    host: IPv4Address
    user: str


@dataclass
class Config:
    database: Database
    filtered_subnets: Collection[IPv4Network]


# separator parameter is defaulted to "." but shown for example
assert unflat_key_value(configuration, separator=".") == {
    "database": {"host": "191.132.67.45", "user": "guest"},
    "filtered_subnets": ["247.252.191.00/24", "207.34.172.00/24"],
}
assert deserialize(
    Config, unflat_key_value(configuration), coercion=True, additional_properties=True
) == Config(
    database=Database(IPv4Address("191.132.67.45"), "guest"),
    filtered_subnets=(
        IPv4Network("247.252.191.00/24"),
        IPv4Network("207.34.172.00/24"),
    ),
)
