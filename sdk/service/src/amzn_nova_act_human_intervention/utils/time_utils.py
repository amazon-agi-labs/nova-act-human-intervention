"""Time utility functions for Nova Act Human Intervention."""


def format_seconds_to_human_readable(seconds: int) -> str:
    """Convert seconds to a human-readable time string.

    Args:
        seconds: Number of seconds to convert

    Returns:
        Human-readable time string (e.g., "2 hours and 30 minutes", "45 minutes")

    Examples:
        >>> format_seconds_to_human_readable(7200)
        '2 hours'
        >>> format_seconds_to_human_readable(5400)
        '1 hour and 30 minutes'
        >>> format_seconds_to_human_readable(2700)
        '45 minutes'
        >>> format_seconds_to_human_readable(30)
        'less than a minute'
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 0 and minutes > 0:
        hour_str = f"{hours} hour{'s' if hours != 1 else ''}"
        min_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        return f"{hour_str} and {min_str}"
    elif hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    elif minutes > 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return "less than a minute"
