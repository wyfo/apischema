from base64 import b64decode

from apischema import deserialize, deserializer
from apischema.conversions import Conversion

deserializer(Conversion(b64decode, source=str, target=bytes))
# Roughly equivalent to:
# def decode_bytes(source: str) -> bytes:
#     return b64decode(source)
# but saving a function call

assert deserialize(bytes, "Zm9v") == b"foo"
