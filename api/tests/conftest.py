"""Test configuration - sets env vars needed by middleware modules."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-key")
