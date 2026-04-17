# Section E - Enrollment and Machine Learning Data Quality

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/enroll.py](../app/enroll.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/enroll.html](../app/web/templates/enroll.html)
- [app/web/templates/persons.html](../app/web/templates/persons.html)
- [app/web/app_factory.py](../app/web/app_factory.py)
- [app/web_run.py](../app/web_run.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/repo.py](../app/db/repo.py)
- [app/ml/preprocess.py](../app/ml/preprocess.py)
- [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)
- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/main.py](../app/main.py)
- [app/core/models.py](../app/core/models.py)
- [app/config.py](../app/config.py)
- [tests/test_enrollment_service.py](../tests/test_enrollment_service.py)
- [tests/test_db_repo.py](../tests/test_db_repo.py)
- [tests/test_ml_logic.py](../tests/test_ml_logic.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_routes.py](../tests/test_routes.py)
- [tests/test_rbac.py](../tests/test_rbac.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)
- [docs/ML_INTEGRATION_LOG.md](../docs/ML_INTEGRATION_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior is reconstructed from BUILD_LOG/SETUP/architecture docs.
- If behavior is implied but not explicitly guaranteed by code/tests/docs, it is marked as INFERENCE.

---

## E1. Initial Single-Image Enrollment System

### Technical evidence summary

Initial enrollment design (Iteration 2) was CLI-driven and single-image oriented:
- CLI entrypoint with one name + one image arg: [app/enroll.py](../app/enroll.py)
- Historical note says detect single face (reject 0 or >1): [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- Setup doc still states exact one-face expectation: [docs/SETUP.md](../docs/SETUP.md)

Current single-image upload compatibility path through web:
- Admin posts one file to `/enroll`; route decodes and passes list length 1 to service with effective `min_captures=1`: [app/web/routes.py](../app/web/routes.py), [app/services/enrollment_service.py](../app/services/enrollment_service.py)

Current code keeps that path as a compatibility wrapper:
- `enroll_from_image(name, image)` calls multi-image function with `min_captures=1`: [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- So single-image flow still exists, but implemented through shared batch service.

### 1. What existed before

Before guided multi-pose web enrollment, the practical enrollment path was:
1. Operator runs CLI (`python -m app.enroll --name ... --image ...`): [app/enroll.py](../app/enroll.py)
2. CLI calls `enroll_from_file(...)`: [app/enroll.py](../app/enroll.py)
3. Service reads image and routes to `enroll_from_image(...)`: [app/services/enrollment_service.py](../app/services/enrollment_service.py)
4. Face detector + recogniser produce one embedding if image quality constraints pass.
5. DB writes/update happen in repositories under `app/db/repo.py`.
6. A single accepted upload adds one raw row in `person_embeddings`, then template is recomputed from all stored raw embeddings for that person and written to `persons.embedding`: [app/services/enrollment_service.py](../app/services/enrollment_service.py), [app/db/repo.py](../app/db/repo.py)

Historical docs confirm original single-image intent:
- Iteration 2 log explicitly describes single-face CLI enrollment: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- Setup still documents exactly one face: [docs/SETUP.md](../docs/SETUP.md)

### 2. What changed

Changed architecture:
- Single-image API is now a wrapper over `enroll_from_multiple_images(...)`: [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- Shared service is used by both CLI and web route (reduced duplicate logic): [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)

Important operational effect:
- Even in single-image mode, service still follows batch commit logic and template recomputation from stored gallery embeddings.

### 3. Why it changed

- To unify CLI and Flask enrollment logic in one service layer.
- To make quality controls reusable for future multi-image enrollment and camera-guided UX.
- To avoid drift where CLI and web would otherwise validate/process images differently.

### 4. What files matter most

- [app/enroll.py](../app/enroll.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

### 5. Useful code/config snippets

Snippet E1-1 from [app/services/enrollment_service.py](../app/services/enrollment_service.py)

```python
def enroll_from_image(name: str, image: np.ndarray) -> EnrollmentResult:
    return enroll_from_multiple_images(name, [image], min_captures=1)
```

Snippet E1-2 from [app/enroll.py](../app/enroll.py)

```python
parser.add_argument("--name", required=True)
parser.add_argument("--image", required=True)
result = enroll_from_file(name=name, image_path=image_path)
```

Snippet E1-3 from [docs/SETUP.md](../docs/SETUP.md)

```text
Each photo must contain exactly one face - the tool rejects 0 or multiple.
```

### 6. How to describe this in report language

- The original enrollment subsystem was intentionally narrow: one operator-supplied portrait was converted into a single enrollment update, prioritizing operational simplicity over capture diversity.
- This later became a compatibility layer on top of a stricter shared enrollment service.

### 7. Limitations / honest weaknesses

- Data quality dependence on one frame made the enrolled identity sensitive to blur, pose, and lighting mismatch.
- Single-shot enrollment under-samples intra-person variation, which weakens robustness for runtime matching.
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) still shows a one-face enrollment flow that does not reflect the full current multi-image web path.
- Unknown/uncertain: full pre-Iteration-2 behavior before SQLite onboarding is not completely reconstructible from current code (only from logs).

---

## E2. Multi-Image Enrollment for Improved Recognition

### Technical evidence summary

Multi-image support was introduced as batch enrollment:
- Core function: `enroll_from_multiple_images(name, images, min_captures=3)`: [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- Web POST accepts both disk uploads and camera blobs in one request: [app/web/routes.py](../app/web/routes.py)
- Service enforces minimum successful captures and rejects low-quality batches before commit.

Validation evidence:
- Success/failure threshold tests in [tests/test_enrollment_service.py](../tests/test_enrollment_service.py)

### 1. What existed before

- Enrollment assumptions were largely one-image-driven (E1 baseline).
- Recognition quality depended on whether that single capture represented typical face appearance.

### 2. What changed

Backend request handling changed in `/enroll` route:
- Collects `images` list + `camera_images` list, concatenates, filters empty files: [app/web/routes.py](../app/web/routes.py)
- Decodes each file bytes to OpenCV image via `decode_uploaded_image`: [app/web/routes.py](../app/web/routes.py), [app/services/enrollment_service.py](../app/services/enrollment_service.py)

Batch quality gate changed in service:
- For each image:
  - Reject if no face.
  - Reject if multiple faces.
  - Align by 5-point landmarks when available; fallback crop by bbox.
  - Embed accepted crop.
- If valid captures < required threshold, return error and do not continue to DB commit path: [app/services/enrollment_service.py](../app/services/enrollment_service.py)

Threshold behavior nuance:
- Service default is `min_captures=3`.
- Route dynamically sets `min_caps = 3 if len(decoded_images) >= 3 else len(decoded_images)`: [app/web/routes.py](../app/web/routes.py)
- This means 1-image or 2-image web submissions can still succeed if all submitted images validate.

### 3. Why it changed

Documented motivations:
- Prevent weak single-frame enrollment from being persisted.
- Improve enrollment robustness by requiring multiple successful captures when available.
- Add a unified atomic-style batch API for CLI + dashboard paths.

Evidence:
- Iteration 13 notes in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- Enrollment UI rationale in [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)

### 4. What files matter most

- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/enroll.py](../app/enroll.py)
- [tests/test_enrollment_service.py](../tests/test_enrollment_service.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)

### 5. Useful code/config snippets

Snippet E2-1 from [app/web/routes.py](../app/web/routes.py)

```python
upload_files = request.files.getlist("images")
camera_files = request.files.getlist("camera_images")
all_files = upload_files + camera_files
valid_files = [f for f in all_files if f and f.filename]
```

Snippet E2-2 from [app/web/routes.py](../app/web/routes.py)

```python
min_caps = 3 if len(decoded_images) >= 3 else len(decoded_images)
result = enroll_from_multiple_images(name=name, images=decoded_images, min_captures=min_caps)
```

Snippet E2-3 from [app/services/enrollment_service.py](../app/services/enrollment_service.py)

```python
if len(valid_embeddings) < min_captures:
    return EnrollmentResult(
        success=False,
        message=f"Only {len(valid_embeddings)}/{len(images)} valid captures obtained..."
    )
```

### 6. How to describe this in report language

- The enrollment pipeline moved from single-sample registration to evidence-based registration: each enrollment request can carry multiple captures, and only batches meeting minimum successful extraction constraints are accepted.
- This directly improves template stability by reducing dependence on one accidental frame condition.

### 7. Limitations / honest weaknesses

- Docs claim strict `min_captures=3`, but route logic downgrades threshold for small submissions; this is less strict than the wording in [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md).
- The function comment says "commit atomically", but repository methods commit per write (`add_embedding` and `update_embedding`), so failure mid-flow can leave partial state.
- Test coverage validates service threshold behavior, but there is little/no direct test that posts real multipart image files through `/enroll` end-to-end.

---

## E3. Camera-Guided Enrollment UX Design

### Technical evidence summary

Enrollment UI provides two operator modes:
- Guided Camera mode (default) with browser camera + pose sequence.
- Manual Upload mode with multi-file input.

Frontend mechanics are implemented in vanilla JS inside [app/web/templates/enroll.html](../app/web/templates/enroll.html). Backend ingestion is the same `/enroll` endpoint in [app/web/routes.py](../app/web/routes.py).

### 1. What existed before

- Earlier flow focused on CLI/manual image upload, without a browser-guided multi-pose capture state machine.
- No integrated on-page capture prompts and no blob-based camera submission path.

### 2. What changed

UI changes:
- Mode toggle buttons: Guided Camera vs Manual Upload.
- Camera startup via `navigator.mediaDevices.getUserMedia(...)`.
- Pose prompts (`Pose 1/5` ... `Pose 5/5`) and step tracking.
- Snapshot capture from `<video>` to `<canvas>`, then `canvas.toBlob('image/jpeg', 0.85)`.
- Submit interception appends each blob as `camera_images` into `FormData` and POSTs to `/enroll`.

Backend changes:
- Route merges `images` and `camera_images` lists then performs shared decode/validation/enrollment.

Access control:
- `/enroll` is admin-only (`@role_required(["admin"])`), with RBAC tested in [tests/test_rbac.py](../tests/test_rbac.py) and [tests/test_routes.py](../tests/test_routes.py).

### 3. Why it changed

- To standardize capture collection for better enrollment data quality (pose diversity, fewer ad-hoc captures).
- To avoid large base64 payloads and send compressed blobs instead.
- To keep implementation simple and framework-light (vanilla JS).

Evidence:
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)

### 4. What files matter most

- [app/web/templates/enroll.html](../app/web/templates/enroll.html)
- [app/web/routes.py](../app/web/routes.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [tests/test_rbac.py](../tests/test_rbac.py)
- [tests/test_routes.py](../tests/test_routes.py)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)

### 5. Useful code/config snippets

Snippet E3-1 from [app/web/templates/enroll.html](../app/web/templates/enroll.html)

```javascript
const capturePrompts = [
  "Pose 1/5: Look straight ahead",
  "Pose 2/5: Turn slightly right",
  "Pose 3/5: Turn slightly left",
  "Pose 4/5: Tilt slightly down",
  "Pose 5/5: Tilt slightly up"
];
```

Snippet E3-2 from [app/web/templates/enroll.html](../app/web/templates/enroll.html)

```javascript
videoStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
canvas.toBlob(blob => {
  capturedBlobs.push(blob);
}, "image/jpeg", 0.85);
```

Snippet E3-3 from [app/web/templates/enroll.html](../app/web/templates/enroll.html)

```javascript
capturedBlobs.forEach((blob, i) => {
  formData.append("camera_images", blob, `cam_capture_${i}.jpg`);
});
fetch("{{ url_for('web.enroll') }}", { method: "POST", body: formData })
```

### 6. How to describe this in report language

- The enrollment interface moved from passive file intake to guided acquisition: operators are prompted through a fixed pose sequence and captures are uploaded as compressed binary blobs into the same backend validation pipeline.
- This is a data collection quality intervention at UI level, not only a backend validation change.

### 7. Limitations / honest weaknesses

- Browser camera access is environment-sensitive (localhost/HTTPS constraints documented in [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)).
- If camera permission is denied, workflow falls back to manual upload only.
- No explicit liveness/anti-spoof checks in this UI flow.
- No frontend image-quality scoring before submit; quality filtering is deferred to backend face detection success.
- Coverage gap: current tests strongly validate RBAC/status behavior of `/enroll`, but not full JS camera flow under browser automation.

---

## E4. Embedding Aggregation and Template Generation

### Technical evidence summary

Storage model is two-layer:
1. `person_embeddings` stores raw per-shot embeddings.
2. `persons.embedding` stores one computed template used at runtime.

Schema evidence:
- `persons` table with unique name and embedding metadata: [app/db/schema.sql](../app/db/schema.sql)
- `person_embeddings` table with FK cascade to persons: [app/db/schema.sql](../app/db/schema.sql)

Aggregation pipeline:
- Enrollment inserts raw embeddings (`add_embedding`) then loads all current raw embeddings and recomputes template via `make_template`, then updates `persons.embedding`: [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- `make_template` uses mean + L2 normalization (not median): [app/ml/preprocess.py](../app/ml/preprocess.py)

Runtime use:
- Pipeline compares incoming embedding against loaded gallery templates (`persons.embedding`) via dot product in recogniser compare: [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)
- Gallery is loaded via provider (`make_enrolled_provider`) and `reload_enrolled()`: [app/db/repo.py](../app/db/repo.py), [app/ml/pipeline.py](../app/ml/pipeline.py)

### 1. What existed before

- Earlier enrollment persisted effectively one active embedding/template per person.
- Multi-shot raw embedding retention and recomputation strategy was introduced later (ML integration phase documented in [docs/ML_INTEGRATION_LOG.md](../docs/ML_INTEGRATION_LOG.md)).

### 2. What changed

Raw embedding persistence:
- `SQLiteEmbeddingRepository.add_embedding(...)` stores float32 bytes with dim/dtype and UTC timestamp.
- Cap policy (`MAX_GALLERY_EMBEDDINGS`) evicts oldest rows before insert.

Template recomputation:
- After inserts, service fetches embeddings oldest-first and computes template:
  - stack embeddings
  - element-wise mean
  - L2 normalize
  - cast float32
- Template pushed back into `persons.embedding`.

Visibility in UI:
- Persons page now displays `embedding_count` from `list_person_summaries()` query, exposing how many raw data points are retained for each identity: [app/db/repo.py](../app/db/repo.py), [app/web/templates/persons.html](../app/web/templates/persons.html)

### 3. Why it changed

- To improve representation quality by aggregating multiple captures instead of trusting a single sample.
- To preserve a lightweight runtime hot path (one template vector per person) while retaining enough raw evidence for recomputation.
- To enforce bounded storage via a cap rather than unbounded growth.

### 4. What files matter most

- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/repo.py](../app/db/repo.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/ml/preprocess.py](../app/ml/preprocess.py)
- [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)
- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/config.py](../app/config.py)
- [tests/test_db_repo.py](../tests/test_db_repo.py)
- [tests/test_ml_logic.py](../tests/test_ml_logic.py)
- [docs/ML_INTEGRATION_LOG.md](../docs/ML_INTEGRATION_LOG.md)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)

### 5. Useful code/config snippets

Snippet E4-1 from [app/ml/preprocess.py](../app/ml/preprocess.py)

```python
stacked = np.stack(embeddings, axis=0)
mean = stacked.mean(axis=0)
norm = np.linalg.norm(mean)
if norm > 0:
    mean = mean / norm
return mean.astype(np.float32)
```

Snippet E4-2 from [app/db/repo.py](../app/db/repo.py)

```python
if current >= max_emb:
    self._conn.execute(
        "DELETE FROM person_embeddings WHERE id IN ("
        "  SELECT id FROM person_embeddings "
        "  WHERE person_id = ? ORDER BY created_at ASC LIMIT ?"
        ")",
        (person_id, excess),
    )
```

Snippet E4-3 from [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)

```python
score = float(np.dot(embedding, person.embedding))
is_match = best_score >= self.similarity_threshold
```

### 6. How to describe this in report language

- Enrollment now separates raw evidence storage from runtime identity representation: multiple raw embeddings are retained per person, then compressed into one normalized template vector for efficient matching.
- Recognition quality gains come indirectly from better enrollment coverage, because the runtime matcher compares against a template built from multiple captures rather than one shot.

### 7. Limitations / honest weaknesses

- Doc/code mismatch: [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md) describes "median-averaged" template, but implementation is arithmetic mean in [app/ml/preprocess.py](../app/ml/preprocess.py).
- Mean aggregation is outlier-sensitive; no robust outlier rejection or weighted strategy is implemented in template computation.
- Cap eviction drops oldest raw embeddings, so long-term appearance variance may be lost in prolonged re-enrollment cycles.
- INFERENCE: new enrollments may not immediately affect live recognition if pipeline process does not call `reload_enrolled()` after dashboard writes (only explicit call site found is pipeline initialization path).
  - Related evidence: [app/ml/pipeline.py](../app/ml/pipeline.py), [app/main.py](../app/main.py), [app/web/app_factory.py](../app/web/app_factory.py), [app/web_run.py](../app/web_run.py)
- Route-level threshold flexibility (`1` or `2` uploads accepted when only that many images submitted) can reduce intended data quality floor.

---

## Cross-cutting findings for Section E synthesis

1. Enrollment quality improvements are real but not absolute.
- Strong improvement: multi-capture support + guided camera capture + template recompute from raw gallery.
- Remaining weakness: route-level threshold relaxation and no outlier-resistant aggregation.

2. Historical documentation has drift.
- Some docs still describe strict one-face/single-shot assumptions or use old terminology.
- Report writing should clearly separate "historical baseline" from "current implementation".

3. Testing strengths and gaps.
- Strength: service-level threshold behavior and DB embedding cap behavior are tested.
- Gap: limited end-to-end multipart `/enroll` tests with actual image payloads and no browser automation coverage for guided camera JS.

4. Config semantics should be written carefully.
- Current code prefers `RECOGNITION_MATCH_THRESHOLD` while still supporting legacy `SV_RECOGNITION_SIM_THRESH` alias in [app/config.py](../app/config.py).
- Setup table still lists old env name, so naming should be clarified in final report text.
