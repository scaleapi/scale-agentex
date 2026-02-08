import json
import re
from typing import Any
from uuid import uuid4

from starlette.datastructures import FormData, Headers, UploadFile

REQUEST_KEY_REGEXP_BLACKLIST = [
    r"api_key",
    r"password",
    r"secret",
    r"token",
    r"authorization",
]


def key_is_blacklisted(key: str):
    for regexp in REQUEST_KEY_REGEXP_BLACKLIST:
        if re.search(regexp, key.lower()):
            return True
    return False


def strip_sensitive_items(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: strip_sensitive_items(v)
            for (k, v) in value.items()
            if not key_is_blacklisted(k)
        }
    if isinstance(value, list):
        return [strip_sensitive_items(e) for e in value]
    if isinstance(value, Headers):
        return Headers(strip_sensitive_items(dict(value)))
    return value


def decode_request_body(request_body: bytes):
    try:
        request_dict = strip_sensitive_items(json.loads(request_body.decode("utf-8")))
    except json.JSONDecodeError:
        request_dict = request_body.decode("utf-8")
    except UnicodeDecodeError:
        request_dict = {}
    return request_dict


def form_data_to_body(form_data: FormData) -> bytes:
    boundary = uuid4().hex
    body = []

    for key, value in form_data.multi_items():
        if isinstance(value, UploadFile):
            part = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"; filename="{value.filename}"\r\n'
                f"Content-Type: {value.content_type}\r\n\r\n"
                "[File contents hidden]\r\n"
            )
        else:
            part = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            )
        body.append(part)

    body.append(f"--{boundary}--\r\n")
    return "\r\n".join(body).encode("utf-8")
