import os
import typing as t
from logging import getLogger

logger = getLogger(__name__)


def string(key: str, default: t.Optional[str] = None) -> str:
    val = os.environ.get(key)
    if not val:
        if default is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return default
    return val


def validate_required_env_vars(
    required_vars: t.List[str],
    optional_vars: t.Optional[t.List[str]] = None
) -> t.Tuple[bool, t.List[str]]:
    """
    Validate that all required environment variables are present.
    
    Args:
        required_vars: List of required environment variable names
        optional_vars: List of optional environment variable names (for logging)
    
    Returns:
        Tuple of (success: bool, missing_vars: List[str])
    """
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if optional_vars:
        for var in optional_vars:
            if not os.environ.get(var):
                logger.warning(f"Optional environment variable not set: {var}")
    
    return len(missing_vars) == 0, missing_vars
