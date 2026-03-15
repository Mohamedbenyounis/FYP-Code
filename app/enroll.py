"""
SecureVision — CLI enrollment tool  (ML Integration).

Usage:
    python -m app.enroll --name "Alice" --image ./photos/alice.jpg
    python -m app.enroll --name "Bob"   --image ./photos/bob.png

The tool:
  1. Loads the image from disk.
  2. Runs SCRFD detection — selects highest-confidence face.
  3. Aligns the face via 5-point landmarks, then embeds via ArcFace.
  4. Stores the raw embedding in ``person_embeddings`` (up to 5 per person).
  5. Recomputes the template in ``persons.embedding`` from all raw shots.

No webcam or live feed is involved.
"""

from __future__ import annotations

import argparse
import sys

from app.services.logging_service import get_logger
from app.services.enrollment_service import enroll_from_file


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="enroll",
        description="Enroll a face identity into the SecureVision database.",
    )
    parser.add_argument(
        "--name", required=True, help="Display name for the enrolled person."
    )
    parser.add_argument(
        "--image", required=True, help="Path to a photo containing a face."
    )
    return parser.parse_args(argv)


def enroll(name: str, image_path: str) -> int:
    """
    Run the enrollment pipeline.

    Returns 0 on success, 1 on error.
    """
    log = get_logger()

    result = enroll_from_file(name=name, image_path=image_path)
    if result.success:
        log.info("Enrollment complete ✓ (id=%s)", result.person_id)
        return 0

    log.error("Enrollment failed: %s", result.message)
    return 1


def main() -> int:
    """CLI entry point."""
    args = _parse_args()
    return enroll(name=args.name, image_path=args.image)


if __name__ == "__main__":
    sys.exit(main())
