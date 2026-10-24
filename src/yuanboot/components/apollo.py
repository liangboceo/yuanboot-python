"""Apollo HTTP configuration source, managed by the shared configuration monitor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote, urlsplit

import httpx
import yaml
from pydantic import BaseModel, Field, SecretStr

from yuanboot.configuration import _set


class ApolloOptions(BaseModel):
    endpoint: str = "http://127.0.0.1:8080"
    appid: str
    cluster: str = "default"
    namespace: str = "application"
    secret: SecretStr = SecretStr("")
    timeout: float = Field(default=5, gt=0)
    poll_interval: float = Field(default=5, gt=0)


class ApolloConfigurationSource:
    def __init__(self, options: ApolloOptions, *, transport=None):
        self.options = options
        self.poll_interval = options.poll_interval
        self.client = httpx.Client(timeout=options.timeout, transport=transport, trust_env=False)

    def load(self):
        options = self.options
        parts = [
            quote(value, safe="") for value in (options.appid, options.cluster, options.namespace)
        ]
        url = options.endpoint.rstrip("/") + "/configs/" + "/".join(parts)
        headers = {}
        secret = options.secret.get_secret_value()
        if secret:
            timestamp = str(int(time.time() * 1000))
            text = timestamp + "\n" + urlsplit(url).path
            signature = base64.b64encode(
                hmac.new(secret.encode(), text.encode(), hashlib.sha1).digest()
            ).decode()
            headers = {
                "Timestamp": timestamp,
                "Authorization": f"Apollo {options.appid}:{signature}",
            }
        response = self.client.get(url, headers=headers)
        if not response.is_success:
            raise RuntimeError(f"Apollo configuration failed (HTTP {response.status_code})")
        values = response.json()["configurations"]
        result = {}
        for key, value in values.items():
            if key == "content" and options.namespace.endswith((".yml", ".yaml", ".json")):
                document = yaml.safe_load(value)
                if not isinstance(document, dict):
                    raise ValueError("Apollo document must contain a mapping")
                result.update(document)
            else:
                _set(result, key, value)
        return result

    def close(self):
        self.client.close()
