"""TOON (Threshold-Optimized Output Notation) encoding system.

This package provides compression for large tool outputs by replacing
arrays exceeding threshold with metadata summaries.
"""

from .encoder import encode_output

__all__ = ["encode_output"]
