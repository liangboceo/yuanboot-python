"""Pooled HTTP clients, optionally resolving service names through discovery."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

try:
    import httpx
except ImportError as exc:
    raise ImportError('HTTP client requires: pip install "yuanboot[http]"') from exc

from yuanboot.configuration import Configuration
from yuanboot.dependency_injection import ServiceProvider


class HttpClient:
    def __init__(self, base_url: str = "", *, discovery=None, timeout: float = 10, transport=None):
        self.base_url = base_url.rstrip("/")
        self.discovery = discovery
        if self.base_url:
            parsed = urlsplit(self.base_url)
            if parsed.scheme not in {"http", "https", "lb"} or not parsed.hostname:
                raise ValueError("Expected http://, https:// or lb://service base URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("Base URL must not contain credentials, query or fragment")
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def request(self, method: str, path: str = "", **kwargs):
        if self.base_url and (urlsplit(path).scheme or path.startswith("//")):
            raise ValueError("Use a relative path with a configured base URL")
        url = self.base_url + "/" + path.lstrip("/") if self.base_url else path
        parsed = urlsplit(url)
        if parsed.scheme == "lb":
            if self.discovery is None:
                raise RuntimeError("lb:// requires a service discovery client")
            instance = self.discovery.select_instance(parsed.hostname)
            host = f"[{instance.ip}]" if ":" in instance.ip else instance.ip
            context = instance.metadata.get("yuanboot_application_context-path", "").rstrip("/")
            url = urlunsplit(
                (
                    "http",
                    f"{host}:{instance.port}",
                    context + parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
        return self.client.request(method, url, **kwargs)

    def get(self, path="", **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path="", **kwargs):
        return self.request("POST", path, **kwargs)

    def close(self):
        self.client.close()


class HttpClientFactory:
    def __init__(self, *, discovery=None, timeout=10):
        self.discovery = discovery
        self.timeout = timeout
        self._clients = []

    def create(self, base_url="") -> HttpClient:
        client = HttpClient(base_url, discovery=self.discovery, timeout=self.timeout)
        self._clients.append(client)
        return client

    def close(self):
        for client in self._clients:
            client.close()
        self._clients.clear()


def add_http_client(services):
    def factory(configuration: Configuration, provider: ServiceProvider):
        discovery = None
        from yuanboot.components.discovery import ServiceDiscovery

        if services.contains(ServiceDiscovery):
            discovery = provider.get_service(ServiceDiscovery)
        elif configuration.get_string("yuanboot.cloud.discovery.type") == "nacos":
            from yuanboot.components.nacos import NacosClient

            discovery = provider.get_service(NacosClient)
        return HttpClientFactory(
            discovery=discovery, timeout=float(configuration.get("yuanboot.httpclient.timeout", 10))
        )

    services.add_singleton(HttpClientFactory, factory)
    return services
