"""
Shared enrollment orchestration service (Iteration 13).

This module centralises face enrollment logic so CLI and Flask routes do not
duplicate detector/recogniser/DB workflows. Contains atomic multi-frame enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app import config
from app.db.migrations import init_db
from app.db.repo import SQLiteEmbeddingRepository, SQLitePersonRepository
from app.ml.detector_scrfd import ModelNotFoundError, SCRFDDetector, select_highest_score
from app.ml.preprocess import align_face_5point, make_template, safe_crop_face
from app.ml.recogniser_arcface import ArcFaceRecogniser
from app.services.logging_service import get_logger


@dataclass
class EnrollmentResult:
    success: bool
    message: str
    person_id: int | None = None


def enroll_from_image(name: str, image: np.ndarray) -> EnrollmentResult:
    """
    Legacy wrapper: Enroll a person from a single in-memory BGR image.
    Uses the multi-image architecture under the hood with a minimum constraint of 1.
    """
    return enroll_from_multiple_images(name, [image], min_captures=1)


def enroll_from_multiple_images(
    name: str, images: list[np.ndarray], min_captures: int = 3
) -> EnrollmentResult:
    """
    Enroll a person atomically from a list of images.
    Requires at least `min_captures` successful face extracts before saving to DB.
    """
    log = get_logger()

    if not images:
        return EnrollmentResult(success=False, message="No images provided")

    try:
        detector = SCRFDDetector()
        recogniser = ArcFaceRecogniser()
    except ModelNotFoundError as exc:
        return EnrollmentResult(success=False, message=f"Model missing: {exc}")

    valid_embeddings = []
    failed_reasons = []

    # 1. Evaluate all images in memory
    for i, img in enumerate(images):
        if img is None or img.size == 0:
            failed_reasons.append(f"Image {i+1} is broken")
            continue

        detections = detector.detect(img)
        if not detections:
            failed_reasons.append(f"Image {i+1}: No face detected")
            continue
            
        if len(detections) > 1:
            failed_reasons.append(f"Image {i+1}: Multiple faces detected")
            continue

        face = select_highest_score(detections)
        if face is None:
            continue

        crop = None
        if face.keypoints is not None:
            crop = align_face_5point(img, face.keypoints)
        if crop is None:
            crop = safe_crop_face(img, face.bbox)
        if crop is None or crop.size == 0:
            failed_reasons.append(f"Image {i+1}: Face crop failed")
            continue

        embedding = recogniser.embed(crop)
        valid_embeddings.append(embedding)

    # 2. Enforce minimum quality threshold
    if len(valid_embeddings) < min_captures:
        err_msg = (
            f"Only {len(valid_embeddings)}/{len(images)} valid captures obtained. "
            f"{min_captures} required. Needs clear, single front-facing portraits."
        )
        if failed_reasons:
            log.warning("Enrollment multi-image failures: %s", " | ".join(failed_reasons))
        return EnrollmentResult(success=False, message=err_msg)

    # 3. Commit atomically to SQLite
    conn = init_db(config.DB_PATH)
    try:
        person_repo = SQLitePersonRepository(conn)
        emb_repo = SQLiteEmbeddingRepository(conn)

        existing = person_repo.get_by_name(name)
        if existing is not None:
            person_id = existing.person_id
        else:
            person = person_repo.add_person(name, valid_embeddings[0]) # init with first
            person_id = person.person_id

        # Insert all new embeddings
        for emb in valid_embeddings:
            emb_repo.add_embedding(person_id, emb)
            
        # Re-calc median template
        all_embeddings = emb_repo.get_embeddings(person_id)
        template = make_template(all_embeddings)
        person_repo.update_embedding(person_id, template)

        log.info("Multi-enrollment updated '%s' with %d shots (id=%d)", 
                 name, len(valid_embeddings), person_id)
        return EnrollmentResult(
            success=True,
            message=f"Successfully enrolled {name} with {len(valid_embeddings)} captures.",
            person_id=person_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Multi-enrollment atomic commit failed")
        return EnrollmentResult(success=False, message=f"Commit error: {exc}")
    finally:
        conn.close()


def decode_uploaded_image(image_bytes: bytes) -> np.ndarray | None:
    """Decode uploaded bytes into an OpenCV BGR image."""
    if not image_bytes:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def enroll_from_file(name: str, image_path: str) -> EnrollmentResult:
    """Enroll a person from an image file path."""
    path = Path(image_path)
    if not path.exists():
        return EnrollmentResult(success=False, message=f"Image not found: {path}")

    image = cv2.imread(str(path))
    if image is None:
        return EnrollmentResult(
            success=False,
            message=f"Failed to read image: {path}",
        )

    return enroll_from_image(name=name, image=image)
