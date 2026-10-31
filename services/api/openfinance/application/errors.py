class ApplicationError(Exception):
    """Error esperado de un caso de uso; la API lo traduce a una respuesta HTTP."""


class AuthenticationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("Email o contraseña incorrectos")


class NotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class InvalidRequestError(ApplicationError):
    pass
