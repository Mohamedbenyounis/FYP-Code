# Iteration 9–11 Evaluation Report

**Date**: 5 April 2026  
**Branch**: `main`  
**Python**: 3.10.8  
**Test Framework**: pytest 9.0.2

---

## 1. Scope

This evaluation covers four iterations of the SecureVision system:

| Iteration | Feature | Module |
|-----------|---------|--------|
| 9 | Multi-Entity Event Management | `app.core.multi_event_manager` |
| 10 | Clip Recording with Pre/Post Buffer | `app.recording.clip_recorder` |
| 11 | Alert Service with Cooldown + Email | `app.services.alert_service` |
| 11b | track_key Propagation | `app.core.event_manager`, `models.py` |

## 2. Evaluation Method

This evaluation is based on **correctness verification through automated testing** — not on a full-system benchmark with live camera and ML inference.

> **Note**: The `python -m app.benchmark_run` command referenced in planning does **not exist** on the current `main` branch. The benchmark tooling was part of the `feature/tracking-iteration-6` branch, which was archived and reset from main. No synthetic microbenchmark has been substituted because it would not represent full-system performance.

The evaluation focuses on:
1. **Functional correctness** — Do the modules behave according to specification?
2. **Edge case resilience** — Does the system survive adversarial inputs?
3. **Anti-spam guarantees** — Is event/alert duplication prevented?
4. **Integration correctness** — Does track_key flow end-to-end?
5. **Known limitations** — What trade-offs were made?

## 3. Test Coverage Summary

| Module | Tests Before | Tests After | New Tests | Status |
|--------|-------------|-------------|-----------|--------|
| `MultiEntityEventManager` | 24 | 39 | +15 | ✅ All pass |
| `AlertService` | 10 | 20 | +10 | ✅ All pass |
| `ClipRecorder` | 2 | 5 | +3 | ✅ All pass |
| `EventManager` | 22 | 22 | — | ✅ All pass |
| **Total** | **58** | **86** | **+28** | ✅ **86/86 pass** |

## 4. Correctness Results by Category

### 4.1 Multi-Face Event Handling

| Scenario | Tested | Result |
|----------|--------|--------|
| Two faces produce independent events | ✅ | Correct — 2 events with distinct track_keys |
| Two unknowns produce 2 independent events | ✅ | Correct — neither suppresses the other |
| Known + unknown co-exist without interference | ✅ | Correct — independent lifecycles |
| Known person leaving does not affect unknown track | ✅ | Correct — remaining entity stays ACTIVE |
| Track maintains identity with gradual movement | ✅ | Correct — same track_key across 6 frames of drift |
| Max entity cap enforced | ✅ | Correct — excess faces ignored |

### 4.2 Alert Suppression

| Scenario | Tested | Result |
|----------|--------|--------|
| Same unknown (same track_key) within cooldown → suppressed | ✅ | Correct |
| Same unknown after cooldown expires → new alert | ✅ | Correct |
| Two different unknowns → 2 independent alerts | ✅ | Correct |
| Three different unknowns → 3 independent alerts | ✅ | Correct |
| Known person cooldown does not affect unknown alerts | ✅ | Correct |
| Unknown cooldown does not affect known person alerts | ✅ | Correct |
| Suppression at boundary (t = cooldown - 0.1s) → suppressed | ✅ | Correct |
| Re-alert at exact boundary (t = cooldown) → fires | ✅ | Correct |
| Complex mixed scenario (3 fire, 1 suppressed, 1 post-cooldown) | ✅ | Correct — 4/5 alerts fired |
| Fallback without track_key → no suppression (event_id based) | ✅ | Correct |

### 4.3 Clip Recording

| Scenario | Tested | Result |
|----------|--------|--------|
| Pre-buffer holds correct number of frames (FPS × pre_sec) | ✅ | Correct — capped at 10 |
| Post-buffer collects frames after event trigger | ✅ | Correct — decrements per frame |
| Clip file exists and is non-zero bytes | ✅ | Correct |
| Writer failure does not create active job | ✅ | Correct — job not stored |

### 4.4 Stability / No-Spam

| Scenario | Tested | Result |
|----------|--------|--------|
| 50 frames same face → exactly 1 event | ✅ | Correct |
| 100 frames × 2 faces → exactly 2 events | ✅ | Correct |
| Entity leaves + returns before cooldown → NO new event | ✅ | Correct |
| Entity leaves + returns after cooldown → NEW event fires | ✅ | Correct |
| Ghost (1-frame) detection → no event, track pruned | ✅ | Correct |
| Crossing paths → no crash, tracks survive | ✅ | Correct |

### 4.5 Crossing Behaviour (Known Limitation)

Two faces crossing paths within `MULTI_FACE_ASSOCIATION_DISTANCE` may result in identity swap. This is a **documented architectural limitation** of centroid-only tracking.

**Test evidence**: `test_crossing_identity_swap_is_known_limitation` explicitly establishes that:
1. Two faces start with distinct track_keys
2. After swapping positions, tracking continues without crash
3. But the track_keys assigned to each physical person may have swapped

This is **not a bug** — it is an expected consequence of the design choice to use centroid-only association without visual feature tracking.

## 5. Performance Notes

No full-system benchmark was run (see Note in Section 2). Relevant performance characteristics from design:

| Parameter | Value | Source |
|-----------|-------|--------|
| ML processing frequency | Every 3rd frame (`PROCESS_EVERY_N_FRAMES`) | `config.py` |
| EventManager window size | 5 observations | `config.py` |
| Confirmation threshold | 3-of-5 (K-of-N) | `config.py` |
| Max concurrent tracks | 10 | `config.py` |
| Clip recording FPS | 15 (subsampled) | `config.py` |
| Alert suppression cooldown | 300s (5 min) | `config.py` |
| Event cooldown | 10s | `config.py` |
| Association distance | 150px | `config.py` |

**Test suite execution time**: 0.45 seconds for 86 tests — indicating that the pure logic components (event management, alert suppression, clip state management) have negligible computational overhead. The real-time performance bottleneck in production is the ML inference pipeline, not the event/alert logic.

## 6. Limitations Summary

| # | Limitation | Severity | Impact | Resolution Path |
|---|-----------|----------|--------|-----------------|
| 1 | Identity swap on crossing | Moderate | Alert suppression may apply wrong history after crossing | Integrate visual tracker (CSRT/KCF) from archived It. 6 branch |
| 2 | No bbox interpolation between ML frames | Moderate | Fast-moving faces may create spurious tracks | Same — visual tracking bridge needed |
| 3 | In-memory suppression state | Low-Moderate | Resets on restart; every entity triggers fresh alert | Persist to DB or use TTL cache |
| 4 | Synchronous clip I/O | Low | Disk write blocks main loop during recording | Async writer thread |
| 5 | Ghost detections consume track slots | Low | False positives temporarily fill entity cap | Gate track creation on minimum detection confidence |
| 6 | Non-unique track_keys across sessions | Low | DB may contain same track_key for different entities | Use UUID or session-prefixed keys |

## 7. Conclusion

The Iteration 9–11b system **works correctly** for its intended scope — a single-camera, single-session face monitoring prototype. All 86 automated tests pass. The core innovations:

- **Per-entity event lifecycle management** (Iteration 9) correctly handles multiple simultaneous faces without cross-interference
- **Alert suppression** (Iteration 11/11b) correctly uses track_key-derived keys to prevent spam while allowing independent alerts for distinct entities
- **Clip recording** (Iteration 10) correctly implements the pre/post buffer pattern

The main weakness is the **centroid-only tracking association**, which is explicitly documented and architecturally isolated for future replacement with visual tracking.
