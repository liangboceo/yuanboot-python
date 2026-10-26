"""Password hashing, signed access tokens, rotating refresh tokens and PNG captcha."""

import base64
import hashlib
import hmac
import io
import os
import secrets
import time

import jwt
from PIL import Image, ImageDraw, ImageFont

from yuanboot import Configuration

from .cache import Cache


def hash_password(password):
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_urlsafe(16)
    digest = base64.b64encode(
        hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    ).decode()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password, encoded):
    if encoded.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, digest = encoded.split("$")
            raw = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
            actual = raw.hex() if len(digest) == 64 else base64.b64encode(raw).decode()
            return hmac.compare_digest(actual, digest)
        except (ValueError, TypeError):
            return False
    # Existing administration accounts can migrate on their first successful login.
    return hmac.compare_digest(
        hashlib.sha256((password + "sendex-salt").encode()).hexdigest(), encoded
    )


def strong_password(password):
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(not c.isalnum() for c in password)
    )


class Security:
    def __init__(self, configuration: Configuration, cache: Cache):
        self.cache = cache
        self.secret = configuration.get_string("admin.jwt_secret")
        self.access_ttl = configuration.get_int("admin.access_ttl", 43200)
        self.refresh_ttl = configuration.get_int("admin.refresh_ttl", 604800)
        if len(self.secret) < 32 or min(self.access_ttl, self.refresh_ttl) < 1:
            raise ValueError(
                "admin.jwt_secret must contain at least 32 characters "
                "and token TTLs must be positive"
            )
        if configuration.profile == "pro" and not os.getenv("ADMIN_JWT_SECRET"):
            raise ValueError("pro requires ADMIN_JWT_SECRET")

    def captcha(self):
        code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        image = Image.new("RGB", (140, 48), (244, 247, 252))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 29)
        except OSError:
            font = ImageFont.load_default(size=29)
        for i, character in enumerate(code):
            draw.text(
                (12 + i * 30, secrets.randbelow(8) + 3), character, font=font, fill=(35, 65, 120)
            )
        for _ in range(6):
            draw.line(
                tuple(secrets.randbelow(140 if i % 2 == 0 else 48) for i in range(4)),
                fill=(140, 160, 190),
            )
        output = io.BytesIO()
        image.save(output, "PNG")
        identifier = secrets.token_urlsafe(24)
        self.cache.put("captcha:" + identifier, code.lower(), 120)
        return {
            "captchaId": identifier,
            "image": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
        }

    def check_captcha(self, identifier, code):
        expected = self.cache.consume("captcha:" + identifier)
        if not expected or not hmac.compare_digest(expected, code.lower()):
            raise ValueError("验证码错误或已过期")

    def tokens(self, user, sid=None):
        sid = sid or secrets.token_urlsafe(24)
        issued = int(time.time())
        claims = {
            "sub": str(user.id),
            "username": user.username,
            "userid": user.id,
            "isAdmin": user.is_admin,
            "tokenType": "admin",
            "ver": user.token_version,
            "sid": sid,
            "iss": "__PROJECT__",
            "iat": issued,
            "exp": issued + self.access_ttl,
        }
        access = jwt.encode(claims, self.secret, algorithm="HS256")
        refresh = secrets.token_urlsafe(48)
        self.cache.put("session:" + sid, user.id, self.refresh_ttl)
        self.cache.put(
            "refresh:" + hashlib.sha256(refresh.encode()).hexdigest(),
            {"user": user.id, "sid": sid, "ver": user.token_version},
            self.refresh_ttl,
        )
        return {"accessToken": access, "refreshToken": refresh, "expires": claims["exp"]}

    def decode(self, token):
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer="__PROJECT__",
                options={"require": ["exp", "sub", "sid", "ver"]},
            )
        except jwt.InvalidTokenError as exc:
            raise PermissionError("登录已过期，请重新登录") from exc
        if self.cache.get("session:" + claims["sid"]) != int(claims["sub"]):
            raise PermissionError("登录已失效")
        return claims

    def consume_refresh(self, token):
        value = self.cache.consume("refresh:" + hashlib.sha256(token.encode()).hexdigest())
        if not value or self.cache.get("session:" + value["sid"]) != value["user"]:
            raise PermissionError("刷新令牌无效或已过期")
        return value
