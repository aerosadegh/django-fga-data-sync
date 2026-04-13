# fga_data_sync/middleware.py
from .conf import get_setting


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
        # 1. Fetch the dynamic dictionary and FGA settings
        header_mappings = get_setting("REQUEST_HEADER_MAPPINGS")
        fga_user_attr = get_setting("FGA_USER_ATTR")
        fga_prefix = get_setting("FGA_USER_PREFIX")

        # 2. Iterate through every mapped header (No hard limits!)
        for header_name, target_attr in header_mappings.items():
            header_value = request.headers.get(header_name)

            # 3. Apply the OpenFGA prefix strictly to the user attribute
            if header_value and target_attr == fga_user_attr:
                header_value = f"{fga_prefix}{header_value}"

            # 4. Dynamically attach the attribute to the Django Request
            setattr(request, target_attr, header_value)

        return self.get_response(request)
