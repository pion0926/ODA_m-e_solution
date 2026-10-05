"""Compatibility import; implementation lives in ai_gateway."""
import sys
from . import ai_gateway
sys.modules[__name__] = ai_gateway
