# Tracking Integration for Alert Suppression (Iteration 11b)

## Problem Statement

The alert suppression system for unknown (unauthorised) identities was broken.

Three strategies had been tried or considered:

| Strategy | Suppression Key | Result |
|---|---|---|
| Global `"unknown"` bucket | All unknowns share one key | ❌ Too coarse — Person A blocks alerts for Person B |
| Per-event UUID (`event.event_id`) | Unique per event | ❌ Too fine — suppression never activates for unknowns |
| **Per-entity track key** | Stable within tracking session | ✅ Correct — same unknown person suppressed, different unknowns independent |

## Root Cause

The `MultiEntityEventManager` already assigned stable per-entity tracking identities (`track_key` like `"face_0"`, `"face_1"`) to each tracked face. These keys were stamped onto `Observation.track_key` before routing to per-face `EventManager` instances.

**However**, the `Event` model had no `track_key` field. When `EventManager._emit_event()` constructed an `Event`, the tracking identity was silently discarded. `AlertService` received events with no way to identify which tracked entity produced them.

## Solution

Thread `track_key` from `Observation` → `EventManager` bookkeeping → `Event` → `AlertService`.

### Data Flow (After Fix)

```
main.py
  → builds per-face Observations (track_key = None at this point)
  → MultiEntityEventManager.update()
    → stamps obs.track_key = "face_0" (centroid association)
    → routes observation to per-face EventManager
    → EventManager._track_best(obs)
      → captures obs.track_key into self._track_key
    → EventManager._emit_event()
      → creates Event(track_key=self._track_key)
  → AlertService.trigger_unauthorised_alert(event)
    → derives suppression key:
        known person:  "person:<person_id>"
        unknown tracked: "unknown_track:<track_key>"
        fallback: "unknown:<event_id>"
```

### Suppression Key Strategy

```python
if event.person_id is not None:
    key = f"person:{event.person_id}"
elif event.track_key is not None:
    key = f"unknown_track:{event.track_key}"
else:
    key = f"unknown:{event.event_id}"
```

- **Known person**: `person_id` is globally stable (DB primary key). Same person across different events → same suppression key.
- **Unknown tracked**: `track_key` (e.g., `"face_3"`) is stable for the lifetime of a tracked entity within a single application session. Same unknown person across frames → same suppression key.
- **Fallback**: `event_id` (UUID) is unique per event. No suppression possible. Only reached if tracking is not active.

## Files Changed

| File | Change |
|---|---|
| `app/core/models.py` | Added `track_key: Optional[str]` to `Event` dataclass |
| `app/core/event_manager.py` | Store and propagate `track_key` from `Observation` to `Event` |
| `app/db/schema.sql` | Added `track_key TEXT` column to `events` table |
| `app/db/migrations.py` | Added idempotent `ALTER TABLE events ADD COLUMN track_key` migration |
| `app/db/repo.py` | Persist and retrieve `track_key` in all event SQL operations |
| `app/services/alert_service.py` | Fixed suppression key derivation using three-tier strategy |
| `app/web/routes.py` | Fixed pre-existing unpacking bug in login route |
| `tests/test_alert_service.py` | Rewritten with comprehensive suppression scenarios |
| `tests/test_event_manager.py` | Added `TestTrackKeyPropagation` class (3 tests) |
| `tests/test_multi_event_manager.py` | Added `TestTrackKeyOnEvents` class (3 tests) |

## What Was NOT Changed

| File | Reason |
|---|---|
| `app/core/multi_event_manager.py` | Already provides stable `track_key` via centroid association. No changes needed. |
| `app/tracking/base.py` | Stub for visual tracking (CSRT/KCF). Out of scope. |
| `app/tracking/tracking_manager.py` | Stub. Out of scope. |
| `app/main.py` | No changes needed — `track_key` flows automatically through the existing pipeline. |

## Known Limitations

### 1. Identity Swap on Crossing (Pre-existing)
If two people physically cross paths, centroid association may swap their `track_key` assignments. This was already a documented limitation from Iteration 9 (nearest-centroid heuristic). Adding visual tracking (CSRT/KCF) would solve this but is a separate iteration.

### 2. Session-Scoped Track Keys
Track keys (`face_0`, `face_1`, etc.) reset when the application restarts. This is acceptable because alert suppression cooldown timers (using `time.monotonic()`) also reset on restart. Both reset together — behaviour is consistent.

### 3. Centroid-Only Association
The system does NOT use visual tracking. Association is purely geometric: "is this detection's centroid close enough to an existing track's last known centroid?" This works well for stationary or slowly-moving faces but degrades when faces cross or move rapidly.

### 4. No Persistent Entity History
Track keys are not globally unique across application restarts. They are meaningful only within a single run session, which is exactly the scope of in-memory alert suppression.

## Verification

```
python -m pytest tests/ --tb=short -q
162 passed in 3.28s
```

Key test scenarios verified:
- ✅ `EventManager` emitted events carry `track_key` from observations
- ✅ `MultiEntityEventManager` emitted events carry correct `track_key` per face
- ✅ Same unknown face (same `track_key`) suppressed within cooldown window
- ✅ Different unknown faces (different `track_key`) generate separate alerts
- ✅ Known identities still suppress by `person_id`
- ✅ Known and unknown suppression keys are independent namespaces
- ✅ Fallback behaviour when `track_key` is `None`
- ✅ No duplicate event spam regression (all pre-existing tests still pass)
