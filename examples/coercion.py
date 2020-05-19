from dataclasses import dataclass, field
from typing import List, Mapping, NewType

from apischema import from_data, items_to_data, output_converter

Secret = NewType("Secret", str)


@output_converter
def hide_secret(_: Secret) -> str:
    return "******"


@dataclass
class Config:
    username: str
    password: Secret
    options: Mapping[str, bool] = field(default_factory=dict)
    authorized_domains: List[str] = field(default_factory=list)


def test_config():
    key_values = {
        "username":                 "wyfo",
        "password":                 "5tr0ngP455w0rd!",
        "options.verbose":          "true",
        "options.execute_order_66": "no",
        "authorized_domains.0":     "fr",
        "authorized_domains.1":     "com",
    }
    assert from_data(Config, items_to_data(key_values.items()), coerce=True) == Config(
        username="wyfo",
        password=Secret("5tr0ngP455w0rd!"),
        options={"verbose": True, "execute_order_66": False},
        authorized_domains=["fr", "com"]
    )
