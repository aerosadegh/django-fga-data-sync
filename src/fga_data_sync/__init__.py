import importlib.metadata
from typing import Any

try:
    # Dynamically fetch the version from the installed package metadata (pyproject.toml).
    # This ensures the python code always exactly matches the built wheel version.
    __version__: str = importlib.metadata.version("django-fga-data-sync")
except importlib.metadata.PackageNotFoundError:
    # Defensive fallback if the module is imported directly without being installed
    # (e.g., during certain local CI/CD steps before the environment is built).
    __version__ = "unknown"


def __getattr__(name: str) -> Any:
    """
    Lazy loading of exports to avoid Django app registry issues.
    
    Args:
        name: The attribute name being accessed on the module.
        
    Returns:
        Any: The requested class or function.
        
    Raises:
        AttributeError: If the requested attribute does not exist in this module.
    """
    if name == "FGAModelSyncMixin":
        from .mixins import FGAModelSyncMixin

        return FGAModelSyncMixin
    if name == "FGAViewMixin":
        from .mixins import FGAViewMixin

        return FGAViewMixin
    if name == "IsFGAAuthorized":
        from .permissions import IsFGAAuthorized

        return IsFGAAuthorized

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FGAModelSyncMixin", "FGAViewMixin", "IsFGAAuthorized", "__version__"]
