# authz_data_sync/__init__.py

__version__ = "0.1.0"


def __getattr__(name):
    """Lazy loading of exports to avoid Django app registry issues."""
    if name == "AuthzSyncMixin":
        from .mixins import AuthzSyncMixin

        return AuthzSyncMixin
    if name == "FGAViewMixin":
        from .mixins import FGAViewMixin

        return FGAViewMixin
    if name == "IsFGAAuthorized":
        from .permissions import IsFGAAuthorized

        return IsFGAAuthorized
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AuthzSyncMixin", "FGAViewMixin", "IsFGAAuthorized", "__version__"]
