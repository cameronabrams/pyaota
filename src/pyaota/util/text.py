"""
Utility text functions for pyaota.
"""

def banner(printf: callable) -> None:
    printf(
        r"""
        (banner here)
        """.strip())

def oxford(items: list[str], conjunction: str = "and") -> str:
    """
    Join a list of strings with commas and an Oxford comma before the conjunction.

    Example:
        oxford(['apples', 'bananas', 'cherries']) 
        returns 'apples, bananas, and cherries'
    """
    if not items:
        return ""
    elif len(items) == 1:
        return items[0]
    elif len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    else:
        return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"