"""tech-skills-br -- Mapeamento de Skills em Tecnologia no Brasil (PIBIC)."""

__version__ = "1.0.0"

from .config import Settings
from .models import Job

__all__ = ["Settings", "Job", "__version__"]
