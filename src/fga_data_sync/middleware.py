# fga_data_sync/middleware.py
import logging

from django.conf import settings

from .conf import get_setting

logger = logging.getLogger(__name__)


class TraefikIdentityMiddleware:
    """Extracts Traefik headers and attaches the FGA user string to the request.

    This middleware reads the X-User-Id header from incoming requests (set by Traefik)
    and formats it as an FGA user string (e.g., "user:123") attached to the request
    object as `request.fga_user`.

    Attributes:
        get_response: The next middleware or view in the chain.

    Example:
        >>> # In settings.py
        >>> MIDDLEWARE = [
        ...     "fga_data_sync.middleware.TraefikIdentityMiddleware",
        ...     ...
        ... ]
        >>> # In settings.py
        >>> FGA_DATA_SYNC = {
        ...     "REQUEST_HEADER_MAPPINGS": {
        ...         "X-User-Id": "auth_user",
        ...         "X-Context-Org-Id": "active_tenant" # for example
        ...     },
        ...     "FGA_USER_ATTR": "auth_user"
        ... }
        >>>
        >>> # In a view
        >>> def my_view(request):
        ...     user_id = request.fga_user  # e.g., "user:abc123"
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        header_mappings = get_setting("REQUEST_HEADER_MAPPINGS")
        fga_user_attr = get_setting("FGA_USER_ATTR")
        fga_prefix = get_setting("FGA_USER_PREFIX")  # e.g., "user:"

        local_dev_config = get_setting("LOCAL_DEV_FALLBACK")

        # 1. Standard Gateway Extraction
        for header_name, target_attr in header_mappings.items():
            header_value = request.headers.get(header_name)

            # 2. Local Development Fallbacks (If Gateway header is missing)
            if not header_value and settings.DEBUG:
                # Fallback A: Use the logged-in Django Database User
                if (
                    local_dev_config.get("USE_DJANGO_USER")
                    and hasattr(request, "user")
                    and request.user.is_authenticated
                ):
                    header_value = str(request.user.id)
                    logger.debug(f"🛠️ Local Dev: Falling back to Django User -> {header_value}")

                # Fallback B: Use a static string
                elif local_dev_config.get("STATIC_USER_ID"):
                    header_value = local_dev_config.get("STATIC_USER_ID")
                    logger.debug(f"🛠️ Local Dev: Falling back to Static User -> {header_value}")

            # 3. Apply the OpenFGA prefix strictly to the user attribute
            if header_value and target_attr == fga_user_attr:
                header_value = f"{fga_prefix}{header_value}"

            # 4. Dynamically attach the attribute to the Django Request
            if header_value:
                setattr(request, target_attr, header_value)

        return self.get_response(request)
