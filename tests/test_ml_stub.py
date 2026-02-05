"""
Tests for ML-disabled mode behaviour.
"""

import pytest
from pathlib import Path

from app.core.models import BoundingBox, Detection
from app.ml.detector_scrfd import ModelNotFoundError, select_largest_face


class TestSelectLargestFace:
    """Test face selection logic."""

    def test_empty_list_returns_none(self):
        """Should return None for empty detection list."""
        result = select_largest_face([])
        assert result is None
