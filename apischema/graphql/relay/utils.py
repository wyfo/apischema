from base64 import b64decode, b64encode

base64_encoding = (
    lambda s: b64decode(s).decode(),
    lambda s: b64encode(s.encode()).decode(),
)
