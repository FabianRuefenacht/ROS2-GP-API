"""Exception classes for the Screening Eagle GP API client."""

class GprApiError(Exception):
    "Base Exception for all GP API client errors."
    
    def __init__(self, message: str, error_code: str = "API-Error", status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        
class GprConnectionError(GprApiError):
    """Raised when the GP API cannot be reached."""

    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="CONNECTION_ERROR",
        )


class GprTimeoutError(GprApiError):
    """Raised when an API request exceeds its timeout."""

    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="TIMEOUT",
        )


class GprHttpError(GprApiError):
    """Raised when the GP API returns an HTTP error."""

    def __init__(
        self,
        message: str,
        status_code: int,
    ):
        super().__init__(
            message,
            error_code="HTTP_ERROR",
            status_code=status_code,
        )


class GprProtocolError(GprApiError):
    """Raised when the GP API returns an unexpected response."""

    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="PROTOCOL_ERROR",
        )


class GprStateError(GprApiError):
    """Raised when an operation is invalid in the current state."""

    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="INVALID_STATE",
        )


class GprValidationError(GprApiError):
    """Raised when API request parameters are invalid."""

    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
        )
