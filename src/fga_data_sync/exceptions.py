class FGAConfigurationError(Exception):  # pragma: no cover
    """Exception raised when FGA configuration is invalid or missing."""

    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.original_exception = original_exception
        if original_exception:
            self.with_traceback(original_exception.__traceback__)
