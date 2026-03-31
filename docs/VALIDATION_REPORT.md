# Validation Report — SecureVision Iterations 9–11b

**Date**: 5 April 2026  
**Author**: Automated Validation Suite + Manual Test Plan  
**Scope**: MultiEntityEventManager (It. 9), ClipRecorder (It. 10), AlertService (It. 11), track_key propagation (It. 11b)

---

## 1. Automated Test Results

**86 tests — ALL PASSING** (0.45s execution time)

### Multi-Entity Event Manager Tests (`test_multi_event_manager.py`)

| # | Test | Purpose | Result |
|---|------|---------|--------|
| 1 | `TestEuclidean::test_same_point` | Geometry helper correctness | ✅ PASS |
| 2 | `TestEuclidean::test_known_distance` | Euclidean distance accuracy | ✅ PASS |
| 3 | `TestSingleFaceLifecycle::test_single_face_confirms_and_emits_event` | K-of-N confirmation works | ✅ PASS |
| 4 | `TestSingleFaceLifecycle::test_single_face_no_event_below_k` | No premature event | ✅ PASS |
| 5 | `TestSingleFaceLifecycle::test_empty_frame_no_crash` | Empty frame resilience | ✅ PASS |
| 6 | `TestTwoFaces::test_two_faces_independent_events` | Two-person independence | ✅ PASS |
| 7 | `TestTwoFaces::test_two_faces_one_leaves` | One leaves, other persists | ✅ PASS |
| 8 | `TestAssociation::test_same_position_stays_on_same_track` | Track stability | ✅ PASS |
| 9 | `TestAssociation::test_far_away_detection_creates_new_track` | New track creation | ✅ PASS |
| 10 | `TestAssociation::test_close_detection_reuses_track` | Track reuse | ✅ PASS |
| 11 | `TestStaleTrackCleanup::test_stale_track_pruned` | Stale cleanup | ✅ PASS |
| 12 | `TestStaleTrackCleanup::test_active_track_not_pruned` | Active track preserved | ✅ PASS |
| 13 | `TestNoEventSpam::test_no_duplicate_events_while_active` | No spam | ✅ PASS |
| 14 | `TestNoEventSpam::test_cooldown_prevents_immediate_refire` | Cooldown suppression | ✅ PASS |
| 15 | `TestMaxEntities::test_respects_max_entities` | Entity cap | ✅ PASS |
| 16 | `TestMixedIdentities::test_unknown_face_fires_unauthorised` | Unknown → unauthorised | ✅ PASS |
| 17 | `TestMixedIdentities::test_mixed_known_unknown_separate_events` | Mixed identity events | ✅ PASS |
| 18 | `TestBackwardCompat::test_observation_track_key_is_set` | track_key assignment | ✅ PASS |
| 19 | `TestBackwardCompat::test_events_have_standard_fields` | Event structure | ✅ PASS |
| 20 | `TestEdgeCases::test_ghost_face_filtered` | Ghost detection pruned | ✅ PASS |
| 21 | `TestEdgeCases::test_crossing_identities_swap_gracefully` | Crossing survival | ✅ PASS |
| 22 | `TestTrackKeyOnEvents::test_single_face_event_has_track_key` | track_key on events | ✅ PASS |
| 23 | `TestTrackKeyOnEvents::test_two_faces_get_different_track_keys` | Distinct keys | ✅ PASS |
| 24 | `TestTrackKeyOnEvents::test_unknown_event_has_stable_track_key` | Unknown gets key | ✅ PASS |
| 25 | `TestMultipleUnknowns::test_two_unknowns_produce_two_events` | 2 unknowns → 2 events | ✅ PASS |
| 26 | `TestMultipleUnknowns::test_two_unknowns_have_distinct_track_keys` | Distinct keys for unknowns | ✅ PASS |
| 27 | `TestMultipleUnknowns::test_two_unknowns_do_not_suppress_each_other` | No cross-suppression | ✅ PASS |
| 28 | `TestKnownUnknownInteraction::test_known_person_does_not_block_unknown_event` | Independence | ✅ PASS |
| 29 | `TestKnownUnknownInteraction::test_known_event_track_key_differs_from_unknown` | Namespace separation | ✅ PASS |
| 30 | `TestKnownUnknownInteraction::test_known_removal_does_not_affect_unknown_tracking` | Independent lifecycle | ✅ PASS |
| 31 | `TestTrackContinuity::test_slight_movement_preserves_track_key` | Movement stability | ✅ PASS |
| 32 | `TestTrackContinuity::test_track_key_consistent_across_observations` | Key consistency | ✅ PASS |
| 33 | `TestCrossingScenarioDetailed::test_crossing_does_not_crash` | Crash resilience | ✅ PASS |
| 34 | `TestCrossingScenarioDetailed::test_crossing_still_emits_events` | Crossing event emission | ✅ PASS |
| 35 | `TestCrossingScenarioDetailed::test_crossing_identity_swap_is_known_limitation` | Identity swap documented | ✅ PASS |
| 36 | `TestLongDurationNoSpam::test_50_frames_single_event` | 50-frame no-spam | ✅ PASS |
| 37 | `TestLongDurationNoSpam::test_100_frames_two_faces_two_events` | 100-frame no-spam | ✅ PASS |
| 38 | `TestLeaveReturnBeforeCooldown::test_same_position_return_before_cooldown_no_new_event` | Cooldown blocks re-fire | ✅ PASS |
| 39 | `TestLeaveReturnAfterCooldown::test_return_after_cooldown_fires_new_event` | Post-cooldown re-fire | ✅ PASS |

### Alert Service Tests (`test_alert_service.py`)

| # | Test | Purpose | Result |
|---|------|---------|--------|
| 1 | `TestAuthorisedIgnored::test_authorised_event_never_triggers` | Authorised skip | ✅ PASS |
| 2 | `TestKnownPersonSuppression::test_known_person_triggers_first_alert` | First alert fires | ✅ PASS |
| 3 | `TestKnownPersonSuppression::test_known_person_suppressed_within_cooldown` | Cooldown suppression | ✅ PASS |
| 4 | `TestKnownPersonSuppression::test_known_person_fires_after_cooldown_expires` | Cooldown expiry | ✅ PASS |
| 5 | `TestUnknownTrackKeySuppression::test_same_unknown_track_key_suppressed` | Per-entity suppression | ✅ PASS |
| 6 | `TestUnknownTrackKeySuppression::test_different_unknown_track_keys_fire_independently` | Independence | ✅ PASS |
| 7 | `TestUnknownTrackKeySuppression::test_unknown_track_key_fires_after_cooldown` | Cooldown expiry | ✅ PASS |
| 8 | `TestUnknownTrackKeySuppression::test_unknown_track_key_does_not_cross_suppress_known` | Namespace isolation | ✅ PASS |
| 9 | `TestFallbackNoTrackKey::test_no_track_key_uses_event_id` | Fallback no-suppression | ✅ PASS |
| 10 | `TestAlertsDisabled::test_alerts_disabled_skips_everything` | Feature flag | ✅ PASS |
| 11 | `TestMultipleUnknownAlerts::test_two_unknowns_at_same_time_both_fire` | 2 unknowns → 2 alerts | ✅ PASS |
| 12 | `TestMultipleUnknownAlerts::test_three_unknowns_three_alerts` | 3 unknowns → 3 alerts | ✅ PASS |
| 13 | `TestMultipleUnknownAlerts::test_same_unknown_twice_only_one_alert` | Same entity suppressed | ✅ PASS |
| 14 | `TestSameUnknownLeaveReturnBeforeCooldown::test_suppressed_within_cooldown_window` | Pre-cooldown suppression | ✅ PASS |
| 15 | `TestSameUnknownLeaveReturnBeforeCooldown::test_suppressed_at_boundary` | Boundary suppression | ✅ PASS |
| 16 | `TestSameUnknownLeaveReturnAfterCooldown::test_fires_after_cooldown_expiry` | Post-cooldown re-fire | ✅ PASS |
| 17 | `TestSameUnknownLeaveReturnAfterCooldown::test_fires_at_exact_boundary` | Exact boundary re-fire | ✅ PASS |
| 18 | `TestKnownDoesNotSuppressUnknown::test_known_cooldown_independent_of_unknown` | Known → unknown isolation | ✅ PASS |
| 19 | `TestKnownDoesNotSuppressUnknown::test_unknown_cooldown_independent_of_known` | Unknown → known isolation | ✅ PASS |
| 20 | `TestKnownDoesNotSuppressUnknown::test_mixed_scenario_four_alerts_expected` | Complex 5-event scenario | ✅ PASS |

### Clip Recorder Tests (`test_clip_recorder.py`)

| # | Test | Purpose | Result |
|---|------|---------|--------|
| 1 | `test_clip_recorder_ring_buffer_and_job` | Full lifecycle | ✅ PASS |
| 2 | `test_clip_recorder_writer_failure_and_path` | Writer failure handling | ✅ PASS |
| 3 | `test_clip_pre_buffer_correct_frame_count` | Pre-buffer capacity | ✅ PASS |
| 4 | `test_clip_post_buffer_continues_after_event` | Post-buffer frame collection | ✅ PASS |
| 5 | `test_clip_file_nonzero_size` | File exists + non-zero | ✅ PASS |

### Event Manager Tests (`test_event_manager.py`)

| # | Test | Purpose | Result |
|---|------|---------|--------|
| 1–22 | All 22 existing tests | State machine correctness, track_key propagation | ✅ ALL PASS |

---

## 2. Manual Test Plan

### Scenario 1: Single Person Test

| Item | Detail |
|------|--------|
| **Setup** | One enrolled person walks into camera view |
| **Expected** | After K frames: 1 authorised event emitted. Person stays in frame → no additional events. Person leaves → track enters COOLDOWN. |
| **Observe** | Dashboard shows exactly 1 event. Console logs show `EVENT` line with `status=authorised`. Preview window shows green bounding box with name label. |
| **Failure Looks Like** | Multiple events for same person. Event fires immediately (before K frames). Event fires after person has been standing still for a long time. |

### Scenario 2: Two People Simultaneous

| Item | Detail |
|------|--------|
| **Setup** | Two enrolled people stand in view simultaneously, well separated (>150px apart in frame) |
| **Expected** | 2 independent authorised events, each with a unique track_key. Both bounding boxes visible. |
| **Observe** | Dashboard shows 2 events. Console shows 2 `EVENT` lines with different `track_key` values. Both bboxes render. |
| **Failure Looks Like** | Only 1 event fires. Both events have the same track_key. One person's bbox merges with the other's. |

### Scenario 3: Unknown Person Alert

| Item | Detail |
|------|--------|
| **Setup** | Unenrolled person walks into view |
| **Expected** | After K frames: 1 unauthorised event + 1 alert in DB. If person stays, no additional alerts (event-level cooldown). |
| **Observe** | Console `ALERT FIRED` log. Dashboard shows alert entry. No repeated alerts for same person standing still. |
| **Failure Looks Like** | No alert fires. Multiple alerts fire for same standing person. Alert fires for enrolled person. |

### Scenario 4: Multiple Unknowns

| Item | Detail |
|------|--------|
| **Setup** | Two unenrolled people stand in view simultaneously |
| **Expected** | 2 unauthorised events. 2 independent alerts (different suppression keys). Neither suppresses the other. |
| **Observe** | 2 `ALERT FIRED` lines in console with different `key=unknown_track:face_X` values. Dashboard shows 2 alerts. |
| **Failure Looks Like** | Only 1 alert fires. Both alerts share the same suppression key. Second person's alert is suppressed by first person's cooldown. |

### Scenario 5: Enter / Leave / Re-enter

| Item | Detail |
|------|--------|
| **Setup** | Person enters view, gets confirmed, leaves frame, waits, re-enters |
| **Expected** | First entry: event fires. If re-entry is within EventManager cooldown (~10s default): no new event. If re-entry is after cooldown: new event fires. |
| **Observe** | Count events in dashboard. Check console timestamps between EVENT lines. |
| **Failure Looks Like** | Event fires immediately on re-entry during cooldown. No event fires on re-entry after cooldown. |

### Scenario 6: Crossing Paths

| Item | Detail |
|------|--------|
| **Setup** | Two people walk past each other (paths cross) |
| **Expected** | System must NOT crash. Both tracks survive. **KNOWN LIMITATION**: identities may swap after crossing because centroid-only association cannot distinguish visual identity when faces are close together. |
| **Observe** | No crash or exception in console. Active track count remains 2. Bounding box labels may swap between the two people — this is expected. |
| **Failure Looks Like** | Application crash. Track count drops to 1 (one track gets lost). Both tracks merge into one. |

### Scenario 7: Noisy Background (Ghost Detections)

| Item | Detail |
|------|--------|
| **Setup** | Camera pointing at scene with occasional false positive detections (posters, patterns, screen reflections) |
| **Expected** | Transient 1–2 frame detections create tracks but never reach K-of-N confirmation threshold. No events emitted for ghosts. Stale tracks are pruned within `lost_frames + 5` frames. |
| **Observe** | Console may show `New track face_X` debug lines that then get `Pruning stale track face_X`. No `EVENT` lines for ghost detections. Track count returns to expected level. |
| **Failure Looks Like** | Unauthorised events fire for posters/walls. Track count grows unbounded. System performance degrades from excess tracks. |

---

## 3. Known Limitations — CRITICAL

> [!CAUTION]
> These are fundamental limitations of the current system. They are NOT bugs — they are architectural constraints that require future work to resolve.

### 3.1 Centroid Tracking Identity Swaps on Crossing

**Severity**: Moderate  
**Module**: `MultiEntityEventManager._associate()`

The nearest-centroid association strategy assigns detections to tracks based solely on Euclidean distance between bounding box centroids. When two people cross paths and their centroids come within `MULTI_FACE_ASSOCIATION_DISTANCE` of each other, the greedy matching algorithm may assign each detection to the wrong track.

**Impact**: After a crossing event, track_key `face_0` may now correspond to the physical person who was previously `face_1`, and vice versa. This means:
- Alert suppression may incorrectly apply the wrong cooldown history
- The event log may show identity discontinuities at crossing points
- Clip recordings may contain footage attributed to the wrong entity

**Mitigation**: This would be resolved by integrating visual trackers (CSRT/KCF from Iteration 6) which maintain appearance-based identity. The tracking branch (`feature/tracking-iteration-6`) was archived but contains the foundation for this work.

### 3.2 No True Visual Tracking

**Severity**: Moderate  
**Module**: Architecture gap

The system has no visual feature tracker (CSRT, KCF, DeepSORT). Bounding box continuity between ML inference cycles is maintained purely by centroid proximity. This means:
- Between ML processing frames (every N-th frame), there is no bbox interpolation
- Fast-moving faces may exceed the association distance and create spurious new tracks
- The `PROCESS_EVERY_N_FRAMES` setting creates blind spots where face movement is untracked

### 3.3 Alert Suppression is Session-Scoped

**Severity**: Low-Moderate  
**Module**: `AlertService._last_alert_time`

The suppression cooldown dictionary (`_last_alert_time`) is stored in-memory. It resets entirely on application restart. This means:
- If the system restarts, every previously-seen entity will trigger a fresh alert on first detection
- There is no persistence of suppression state across sessions
- In a multi-process deployment (not currently supported), each process would have independent suppression state

### 3.4 Synchronous Clip Writing Overhead

**Severity**: Low  
**Module**: `ClipRecorder.feed_frame()`

Video frame writing (`cv2.VideoWriter.write()`) happens synchronously in the main loop's call to `feed_frame()`. During active recording jobs:
- Each `feed_frame()` call performs a disk I/O write per active job
- Multiple concurrent jobs multiply this overhead
- On slow storage (e.g., SD card, network drive), this could cause frame drop

**Mitigation**: The `CLIP_TARGET_FPS` subsampling reduces the number of write operations, but the writes themselves are blocking. A dedicated writer thread or async I/O queue would eliminate this bottleneck.

### 3.5 Ghost Detections Consume Track Slots

**Severity**: Low  
**Module**: `MultiEntityEventManager`

False positive detections (face-like patterns in backgrounds) do create temporary tracks that consume slots against the `MULTI_FACE_MAX_ENTITIES` cap. While these are pruned after `lost_frames + 5` frames, a burst of ghost detections could temporarily:
- Fill all entity slots, preventing real faces from being tracked
- Create unnecessary EventManager instances (memory overhead)

The K-of-N confirmation threshold prevents ghost detections from producing events, but the track allocation itself is not gated.

### 3.6 track_key is Not Globally Unique Across Sessions

**Severity**: Low  
**Module**: `MultiEntityEventManager._make_track_key()`

Track keys are generated as `face_0`, `face_1`, etc., with a simple counter that resets on instance creation. If the system restarts, `face_0` will be reused for a potentially different physical person. The `events` table in the database will contain multiple rows with the same `track_key` value but representing different entities.

---

## 4. What Works

| Capability | Status | Evidence |
|------------|--------|----------|
| Multi-face event handling | ✅ Working | 39 tests prove independent per-face lifecycles |
| Per-entity alert suppression (unknown) | ✅ Working | 20 tests prove track_key-based cooldown |
| Per-entity alert suppression (known) | ✅ Working | Tests prove person_id-based cooldown |
| Known/unknown namespace isolation | ✅ Working | `person:X` and `unknown_track:Y` keys are independent |
| Clip pre-buffer recording | ✅ Working | Ring buffer correctly holds N pre-event frames |
| Clip post-buffer recording | ✅ Working | Post-event frames collected until job completes |
| Clip file generation | ✅ Working | Files exist and have non-zero size |
| K-of-N confirmation (no ghost events) | ✅ Working | 1-frame detections never produce events |
| Stale track cleanup | ✅ Working | Unused tracks are pruned after threshold |
| Event spam prevention | ✅ Working | 100-frame sustained presence produces exactly 1 event per entity |
| track_key propagation (Observation → Event → Alert) | ✅ Working | End-to-end flow verified |
| Crossing path survival | ✅ Working | System does not crash during crossing scenarios |
| Max entity cap enforcement | ✅ Working | Beyond max_entities, new faces are ignored |

## 5. What Fails / Needs Future Work

| Issue | Severity | Path Forward |
|-------|----------|--------------|
| Identity swap on crossing | Moderate | Integrate visual tracker (CSRT/KCF from It. 6 branch) |
| No bbox interpolation between ML frames | Moderate | Same as above — tracking layer needed |
| In-memory suppression state (lost on restart) | Low-Moderate | Persist `_last_alert_time` to DB or add a simple TTL cache |
| Synchronous clip I/O | Low | Async writer thread |
| Ghost detections consume track slots | Low | Gate track creation on minimum confidence threshold |
| Non-unique track_keys across sessions | Low | Use UUID-based track keys or session-prefixed keys |

## 6. What is Acceptable for Current Scope

The system is a prototype for a final-year project. The following tradeoffs are **acceptable** given the scope:

1. **Centroid-only association** — Acceptable as a first implementation. The code clearly documents the limitation and the architecture supports plugging in a visual tracker.
2. **In-memory suppression** — Acceptable for single-session operation. The system does not claim multi-session persistence.
3. **Synchronous clip writing** — Acceptable at 15 FPS target recording rate with typical webcam workloads. Would need to be revisited for multi-camera deployment.
4. **Sequential main loop (no async)** — Acceptable for a single-camera prototype. The architecture isolates concerns enough to add parallelism later.
