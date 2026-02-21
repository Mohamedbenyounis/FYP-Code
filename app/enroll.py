"""
SecureVision — CLI enrollment tool  (Iteration 2).

Usage:
    python -m app.enroll --name "Alice" --image ./photos/alice.jpg
    python -m app.enroll --name "Bob"   --image ./photos/bob.png

The tool:
  1. Loads the image from disk.
  2. Runs SCRFD detection — rejects if 0 or >1 faces are found.
  3. Crops + embeds the single face via ArcFace.
  4. Stores the (name, embedding) in the SQLite database.

No webcam or live feed is involved.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np

from app import config
from app.db.migrations import init_db
from app.db.repo import SQLitePersonRepository
from app.ml.detector_scrfd import ModelNotFoundError, SCRFDDetector, select_largest_face
from app.ml.recogniser_arcface import ArcFaceRecogniser
from app.ml.preprocess import safe_crop_face
from app.services.logging_service import get_logger


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="enroll",
        description="Enroll a face identity into the SecureVision database.",
    )
    parser.add_argument(
        "--name", required=True, help="Display name for the enrolled person."
    )
    parser.add_argument(
        "--image", required=True, help="Path to a photo containing exactly one face."
    )
    return parser.parse_args(argv)


def enroll(name: str, image_path: str) -> int:
    """
    Run the enrollment pipeline.

    Returns 0 on success, 1 on error.
    """
    log = get_logger()

    # 1. Validate image path -----------------------------------------------
    img_path = Path(image_path)
    if not img_path.exists():
        log.error("Image not found: %s", img_path)
        return 1

    img = cv2.imread(str(img_path))
    if img is None:
        log.error("Failed to read image (unsupported format?): %s", img_path)
        return 1

    log.info("Loaded image: %s (%dx%d)", img_path.name, img.shape[1], img.shape[0])

    # 2. Load ML models ----------------------------------------------------
    try:
        detector = SCRFDDetector()
    except ModelNotFoundError as exc:
        log.error("Cannot enroll without detector model: %s", exc)
        return 1

    try:
        recogniser = ArcFaceRecogniser()
    except ModelNotFoundError as exc:
        log.error("Cannot enroll without recogniser model: %s", exc)
        return 1

    # 3. Detect faces — must be exactly one --------------------------------
    detections = detector.detect(img)

    if len(detections) == 0:
        log.error("No faces detected in '%s' — cannot enroll.", img_path.name)
        return 1

    if len(detections) > 1:
        log.error(
            "Multiple faces detected (%d) in '%s' — provide a photo with "
            "exactly ONE face.",
            len(detections),
            img_path.name,
        )
        return 1

    face = detections[0]
    log.info(
        "Detected 1 face | conf=%.2f | bbox=%s",
        face.confidence,
        face.bbox.as_tuple(),
    )

    # 4. Crop & embed ------------------------------------------------------
    crop = safe_crop_face(img, face.bbox)
    if crop.size == 0:
        log.error("Face crop failed (bbox out of bounds?)")
        return 1

    embedding = recogniser.embed(crop)
    log.info("Generated 512-d embedding (norm=%.4f)", np.linalg.norm(embedding))

    # 5. Store in database -------------------------------------------------
    conn = init_db(config.DB_PATH)
    repo = SQLitePersonRepository(conn)

    existing = repo.get_by_name(name)
    if existing is not None:
        log.warning(
            "Person '%s' already exists (id=%d). Updating embedding.",
            name,
            existing.person_id,
        )
        repo.update_embedding(existing.person_id, embedding)
        log.info("Updated embedding for '%s'", name)
    else:
        person = repo.add_person(name, embedding)
        log.info("Enrolled '%s' as person id=%d", person.name, person.person_id)

    conn.close()

    log.info("Enrollment complete ✓")
    return 0


def main() -> int:
    """CLI entry point."""
    args = _parse_args()
    return enroll(name=args.name, image_path=args.image)


if __name__ == "__main__":
    sys.exit(main())
