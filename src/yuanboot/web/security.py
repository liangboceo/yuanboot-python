from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer


class JwtBearer(HTTPBearer):
    """JWT signature/expiry verification with an explicit algorithm allowlist."""

    def __init__(
        self,
        secret: str,
        *,
        algorithms: list[str] | None = None,
        issuer: str | None = None,
        audience: str | None = None,
    ):
        super().__init__(scheme_name="BearerAuth", auto_error=False)
        try:
            import jwt
        except ImportError as exc:
            raise ImportError('JWT requires: pip install "yuanboot[jwt]"') from exc
        if not secret:
            raise ValueError("JWT signing key must not be empty")
        self.jwt = jwt
        self.secret = secret
        self.algorithms = algorithms if algorithms is not None else ["HS256"]
        if not self.algorithms or any(a.lower() == "none" for a in self.algorithms):
            raise ValueError("JWT requires an explicit signed algorithm")
        self.issuer = issuer
        self.audience = audience

    async def __call__(self, request: Request) -> dict:
        credentials = await super().__call__(request)
        if credentials:
            try:
                return self.jwt.decode(
                    credentials.credentials,
                    self.secret,
                    algorithms=self.algorithms,
                    issuer=self.issuer,
                    audience=self.audience,
                    options={"require": ["exp"]},
                )
            except self.jwt.InvalidTokenError:
                pass
        raise HTTPException(
            401, "Invalid or missing bearer token", headers={"WWW-Authenticate": "Bearer"}
        )
