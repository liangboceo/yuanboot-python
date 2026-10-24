"""Deployment environments shared by configuration, CLI and registration metadata."""

PROFILES = ("dev", "fat", "uat", "pro")


def validate_profile(profile: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f"Profile must be one of {', '.join(PROFILES)}; got {profile!r}")
    return profile
