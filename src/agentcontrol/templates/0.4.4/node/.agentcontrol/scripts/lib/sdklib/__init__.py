"""Internal SDK library for high-performance operations."""

__all__ = ["task_main"]


def task_main(argv: list[str] | None = None) -> int:
    """Lazy wrapper to main CLI (for import convenience)."""

    from .task_cli import main  # local import to avoid runpy warnings

    return main(argv)
