# ML Integration — Design Log

> **Date:** 2026-03-12  
> **Iteration:** ML Integration (between Iteration 3 and 4)  
> **Status:** Implemented

---

## 1. Detector — SCRFD det_500m

| Property | Value |
|----------|-------|
| Model file | `models/det_500m.onnx` (from `buffalo_s`) |
| Architecture | SCRFD, 500 K params |
| Input | `[1, 3, H, W]` float32, **RGB (x − 127.5) / 128.0** (InsightFace convention) |
| Input size | 640 × 640 (dynamic spatial dims in ONNX) |
| Outputs | 9 heads: 3 strides (8, 16, 32) × {scores, bboxes, keypoints} |
| Anchor layout | 2 anchors per feature-map cell per stride |
| Score format | Post-sigmoid, `[0, 1]` |
| BBox format | Distance offsets `(left, top, right, bottom)` — multiply by stride, then decode relative to anchor centre |
| Keypoints | 5-point `(x_offset, y_offset)` × 5 — multiply by stride, add anchor centre |
| Confidence threshold | 0.45 (`SV_DETECTION_CONF_THRESH`) |
| NMS IoU threshold | 0.4 (`SV_NMS_IOU_THRESH`) |

### Anchor Decode Pseudocode

```
for stride in [8, 16, 32]:
    fh, fw = 640/stride, 640/stride
    cx = col_index * stride   (repeated × 2 anchors)
    cy = row_index * stride
    
    x1 = cx - raw_left  * stride
    y1 = cy - raw_top   * stride
    x2 = cx + raw_right * stride
    y2 = cy + raw_bottom* stride
    
    kp_x[i] = cx + raw_kps[2i]   * stride
    kp_y[i] = cy + raw_kps[2i+1] * stride
```

### Adaptive Detection-Only Lighting Compensation (2026-03-16)

To improve detection robustness in strongly backlit scenes without paying
the cost of always running detection twice, the pipeline now uses a cheap
per-frame lighting gate.

Added behavior:

- Compute grayscale brightness statistics before detection:
  - `global_mean` over the full frame
  - `center_mean` over the central 50% region
  - `backlit_score = global_mean - center_mean`
- If the frame is likely backlit, detection input is enhanced using one
  configured mode (`none`, `clahe`, `gamma`).
- If not backlit, detector runs on the raw frame as before.

Decision trigger:

- `(global_mean >= BRIGHT_GLOBAL_THRESHOLD and center_mean <= DARK_CENTER_THRESHOLD)`
  OR
- `backlit_score >= BACKLIT_SCORE_THRESHOLD`

Why this is cheaper than a fallback second pass:

- No default double inference per frame.
- Only one detector pass is executed.
- Extra work is limited to cheap grayscale stats and optional lightweight
  enhancement when the heuristic triggers.

Important scope boundary:

- This preprocessing is **detection-only**.
- Recognition/alignment still consume the original frame path, preserving
  ArcFace embedding behavior and enrollment compatibility.

Known limitations:

- Brightness heuristic is intentionally simple; it may miss some hard cases
  (e.g., off-center subject, complex mixed lighting).
- Thresholds are environment dependent and should be tuned via config/env.

---

## 2. Recogniser — ArcFace w600k_mbf

| Property | Value |
|----------|-------|
| Model file | `models/w600k_mbf.onnx` (from `buffalo_s`) |
| Architecture | MobileFaceNet |
| Input | `[N, 3, 112, 112]` float32 |
| Preprocessing | BGR → RGB, `(x − 127.5) / 127.5` (maps to [-1, 1]) |
| Output | `[1, 512]` float32 — L2-normalised post-inference |
| Similarity threshold | 0.25 (`SV_RECOGNITION_SIM_THRESH`) |

---

## 3. Face Alignment

### 5-point (runtime)

- Uses `cv2.estimateAffinePartial2D` to compute a similarity transform
  from the 5 detected keypoints to the ArcFace canonical landmarks:
  ```
  ARCFACE_REF = [[38.29, 51.70], [73.53, 51.50], [56.03, 71.74],
                 [41.55, 92.37], [70.73, 92.20]]
  ```
- Output: `(112, 112, 3)` BGR crop, geometrically normalised.

### 2-point (fallback / GT mode)

- Estimates eye centres from the bounding box (35 % from top, ±17.5 % from centre).
- Same similarity transform targeting the two eye reference points.
- Used when keypoints are unavailable.

---

## 4. Template Generation

Each enrolled person can have up to `MAX_GALLERY_EMBEDDINGS` (5) raw
per-shot embeddings stored in the `person_embeddings` table.

**Template computation:**
1. Retrieve all raw embeddings for the person.
2. Compute the element-wise mean → `(512,)`.
3. L2-normalise.
4. Store in `persons.embedding`.

The pipeline's `make_enrolled_provider` reads from `persons.embedding`,
so the comparison hot-path is unchanged.

---

## 5. Decision Rule

**Authorised** iff:
- `primary_detection` exists (selected via `select_largest_face`)
- `recognition.is_match == True`
- `recognition.score ≥ RECOGNITION_SIM_THRESH (0.25)`

**Unknown** iff:
- No `primary_detection`, OR
- No recognition result, OR
- `recognition.score < threshold`

The rule is based on the **selected primary face**, not the raw
detection count.  Multiple detections are permitted; the runtime
always picks the largest-area face as the primary.

---

## 6. Schema Change

New table `person_embeddings`:

```sql
CREATE TABLE IF NOT EXISTS person_embeddings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER NOT NULL,
    embedding     BLOB    NOT NULL,
    embedding_dim INTEGER NOT NULL,
    dtype         TEXT    NOT NULL DEFAULT 'float32',
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);
```

The existing `persons.embedding` column is retained as the **computed
template** (mean of raw embeddings, L2-normalised).
