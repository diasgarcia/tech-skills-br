"""vagas-tech-junior-2026 -- qual area de tech mais contrata junior no Brasil."""

__version__ = "1.0.0"

from .config import Settings
from .models import Job

__all__ = ["Settings", "Job", "__version__"]
