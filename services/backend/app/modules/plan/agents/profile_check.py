def check_profile(profile: dict | None) -> list[str]:
    """Return list of missing required profile fields (identity, purpose)."""
    if not profile:
        return ["identity", "purpose"]
    missing = []
    if not (profile.get("identity") or "").strip():
        missing.append("identity")
    if not (profile.get("purpose") or "").strip():
        missing.append("purpose")
    return missing
