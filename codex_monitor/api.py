from __future__ import annotations

import sys

from . import api_app


sys.modules[__name__] = api_app
