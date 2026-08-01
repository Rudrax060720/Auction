def user_display_name(username: str | None, first_name: str | None) -> str:
    """Consistent way to display a user across log messages, broadcasts, etc."""
    if username:
        return f"@{username}"
    return first_name or "Unknown"

# Add more shared formatting helpers here as commands need them —
# e.g. escaping Markdown, formatting durations/timestamps, pluralizing counts.