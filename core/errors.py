class FrameworkError(Exception):
    """Base class: every expected failure is a FrameworkError with a message a user can act on."""


class ConfigError(FrameworkError):
    def __init__(self, problems, source=""):
        self.problems = list(problems) if not isinstance(problems, str) else [problems]
        self.source = str(source)
        head = f"Invalid channel config {self.source}:" if source else "Invalid channel config:"
        super().__init__(head + "\n  - " + "\n  - ".join(self.problems))


class SecretsError(FrameworkError):
    pass


class GuardError(FrameworkError):
    """Safety guard tripped (e.g. authenticated YouTube channel != configured channel). Nothing was uploaded."""


class GateError(FrameworkError):
    """A mandatory gate (research / source check) is missing or failed."""


class BudgetError(FrameworkError):
    pass


class PipelineError(FrameworkError):
    pass
