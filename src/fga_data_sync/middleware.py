# fga_data_sync/middleware.py


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
        >>>
        >>> # In a view
        >>> def my_view(request):
        ...     user_id = request.fga_user  # e.g., "user:abc123"
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        dij_user_id = request.headers.get("X-User-Id")

        if dij_user_id:
            request.fga_user = f"user:{dij_user_id}"
        else:
            request.fga_user = None

        return self.get_response(request)
