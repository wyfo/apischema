from base64 import b64decode, b64encode


def decode_base_64(s: str) -> str:
    return b64decode(s).decode()


def encode_base64(s: str) -> str:
    return b64encode(s.encode()).decode()


base64_encoding = (decode_base_64, encode_base64)
