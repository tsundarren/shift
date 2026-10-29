class NotFound(Exception):
    """404: the thing asked about doesn't exist."""


class Invalid(Exception):
    """422: the request is well-formed but breaks a rule (bad time, untrained pin, ...)."""


class Conflict(Exception):
    """409: the request is fine but the scheduler couldn't satisfy it."""
