from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .models import ApiToken


def get_user_from_authorization_header(request) -> AbstractBaseUser | None:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        return None

    scheme, _, token_key = authorization.partition(" ")
    if scheme.lower() not in {"token", "bearer"} or not token_key.strip():
        return None

    token = ApiToken.objects.select_related("user").filter(key=token_key.strip()).first()
    if token is None or not token.user.is_active:
        return None

    return token.user
