# __init__.py

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy loading of exports to avoid Django app registry issues."""
    if name == "FGASyncMixin":
        from .mixins import FGASyncMixin

        return FGASyncMixin
    if name == "FGAViewMixin":
        from .mixins import FGAViewMixin

        return FGAViewMixin
    if name == "IsFGAAuthorized":
        from .permissions import IsFGAAuthorized

        return IsFGAAuthorized

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FGASyncMixin", "FGAViewMixin", "IsFGAAuthorized", "__version__"]
