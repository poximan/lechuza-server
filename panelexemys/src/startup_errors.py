class PanelexemysStartupError(RuntimeError):
    """Error esperado de arranque que debe mostrarse sin traceback."""


class PanelexemysPersistenceError(PanelexemysStartupError):
    """Error esperado cuando la persistencia local no es escribible."""
