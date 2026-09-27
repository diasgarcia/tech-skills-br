"""tech-skills-br -- Mapeamento de Skills em Tecnologia no Brasil."""

__version__ = "1.0.0"

__all__ = ["Settings", "Job", "__version__"]


def __getattr__(name: str):
    """Carrega a API publica sem impor dependencias a submodulos independentes."""
    if name == "Settings":
        from .config import Settings

        return Settings
    if name == "Job":
        from .models import Job

        return Job
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
