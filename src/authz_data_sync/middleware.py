# authz_data_sync/middleware.py


class TraefikIdentityMiddleware:
    """Extracts Traefik headers and attaches the FGA user string to the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        dij_user_id = request.headers.get("X-User-Id")

        if dij_user_id:
            # Developers now just use `request.fga_user` in any view!
            request.fga_user = f"user:{dij_user_id}"
        else:
            request.fga_user = None

        return self.get_response(request)
