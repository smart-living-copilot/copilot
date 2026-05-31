from urllib.parse import unquote


def decode_thing_id(thing_id: str) -> str:
    return unquote(thing_id)
