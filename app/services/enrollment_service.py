"""
Shared enrollment orchestration service (Iteration 5).

This module centralises face enrollment logic so CLI and Flask routes do not
duplicate detector/recogniser/DB workflows.
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
    Enroll a person from an in-memory BGR image.

    Returns an EnrollmentResult with success flag and human-readable message.
    """
    log = get_logger()

    if image is None or image.size == 0:
        return EnrollmentResult(success=False, message="Invalid or empty image")

    try:
        detector = SCRFDDetector()
        recogniser = ArcFaceRecogniser()
    except ModelNotFoundError as exc:
        return EnrollmentResult(success=False, message=f"Model missing: {exc}")

    detections = detector.detect(image)
    if not detections:
        return EnrollmentResult(success=False, message="No face detected")

    face = select_highest_score(detections)
    if face is None:
        return EnrollmentResult(success=False, message="Face selection failed")

    crop = None
    if face.keypoints is not None:
        crop = align_face_5point(image, face.keypoints)
    if crop is None:
        crop = safe_crop_face(image, face.bbox)
    if crop is None or crop.size == 0:
        return EnrollmentResult(success=False, message="Face crop failed")

    embedding = recogniser.embed(crop)

    conn = init_db(config.DB_PATH)
    try:
        person_repo = SQLitePersonRepository(conn)
        emb_repo = SQLiteEmbeddingRepository(conn)

        existing = person_repo.get_by_name(name)
        if existing is not None:
            person_id = existing.person_id
        else:
            person = person_repo.add_person(name, embedding)
            person_id = person.person_id

        emb_repo.add_embedding(person_id, embedding)
        all_embeddings = emb_repo.get_embeddings(person_id)
        template = make_template(all_embeddings)
        person_repo.update_embedding(person_id, template)

        log.info("Enrollment service updated '%s' (id=%d)", name, person_id)
        return EnrollmentResult(
            success=True,
            message="Enrollment completed",
            person_id=person_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Enrollment service failed")
        return EnrollmentResult(success=False, message=f"Enrollment error: {exc}")
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
