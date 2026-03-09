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
from pathlib import Path

import cv2
import numpy as np

from app import config
from app.db.migrations import init_db
from app.db.repo import SQLiteEmbeddingRepository, SQLitePersonRepository
from app.ml.detector_scrfd import ModelNotFoundError, SCRFDDetector, select_highest_score
from app.ml.recogniser_arcface import ArcFaceRecogniser
from app.ml.preprocess import align_face_5point, safe_crop_face, make_template
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
        "--image", required=True, help="Path to a photo containing a face."
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

    # 3. Detect faces — select highest-confidence face ---------------------
    detections = detector.detect(img)

    if len(detections) == 0:
        log.error("No faces detected in '%s' — cannot enroll.", img_path.name)
        return 1

    face = select_highest_score(detections)
    if face is None:
        log.error("Face selection failed.")
        return 1

    if len(detections) > 1:
        log.warning(
            "Multiple faces detected (%d) — using highest-confidence "
            "(conf=%.2f).",
            len(detections),
            face.confidence,
        )

    log.info(
        "Selected face | conf=%.2f | bbox=%s",
        face.confidence,
        face.bbox.as_tuple(),
    )

    # 4. Align & embed -----------------------------------------------------
    crop = None
    if face.keypoints is not None:
        crop = align_face_5point(img, face.keypoints)
    if crop is None:
        log.warning("5-point alignment failed — falling back to bbox crop")
        crop = safe_crop_face(img, face.bbox)
    if crop.size == 0:
        log.error("Face crop failed (bbox out of bounds?)")
        return 1

    embedding = recogniser.embed(crop)
    log.info("Generated 512-d embedding (norm=%.4f)", np.linalg.norm(embedding))

    # 5. Store in database -------------------------------------------------
    conn = init_db(config.DB_PATH)
    try:
        person_repo = SQLitePersonRepository(conn)
        emb_repo = SQLiteEmbeddingRepository(conn)

        existing = person_repo.get_by_name(name)
        if existing is not None:
            person_id = existing.person_id
            log.info(
                "Person '%s' already exists (id=%d). Adding new shot.",
                name, person_id,
            )
        else:
            # First enrollment — create person with this embedding as
            # the initial template.
            person = person_repo.add_person(name, embedding)
            person_id = person.person_id
            log.info("Created person '%s' (id=%d)", name, person_id)

        # Store raw embedding (MAX_GALLERY_EMBEDDINGS enforced internally)
        emb_repo.add_embedding(person_id, embedding)

        # Recompute template from all raw embeddings ----------------------
        all_embs = emb_repo.get_embeddings(person_id)
        template = make_template(all_embs)
        person_repo.update_embedding(person_id, template)
        log.info(
            "Template updated for '%s' (%d/%d shots)",
            name, len(all_embs), config.MAX_GALLERY_EMBEDDINGS,
        )
    finally:
        conn.close()

    log.info("Enrollment complete ✓")
    return 0


def main() -> int:
    """CLI entry point."""
    args = _parse_args()
    return enroll(name=args.name, image_path=args.image)


if __name__ == "__main__":
    sys.exit(main())
