class ApplicationError(Exception):
    """Error esperado de un caso de uso; la API lo traduce a una respuesta HTTP."""


class AuthenticationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("Email o contraseña incorrectos")


class NotFoundError(ApplicationError):
    pass


class ForbiddenError(ApplicationError):
    """La persona está identificada pero su rol no permite esta acción (ADR-0026)."""


class ConflictError(ApplicationError):
    pass


class InvalidRequestError(ApplicationError):
    pass


class WrongPasswordError(InvalidRequestError):
    """La contraseña actual no coincide al cambiarla. 422 y no 401: un 401 cerraría la sesión
    en la web. Cuenta como intento fallido para el límite de intentos."""


class AggregatorError(ApplicationError):
    """El agregador bancario no respondió o rechazó la petición. El mensaje es apto para la
    persona (nunca lleva credenciales ni el cuerpo de la respuesta)."""
