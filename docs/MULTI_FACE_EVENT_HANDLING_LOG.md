# Multi-Face Event Handling Design Log

## Context

This document records the architectural decisions and limitations of
**Iteration 9: Multi-Face Event Handling**, implemented on the experimental
branch `feature/multi-face-event-handling`.

---

## Why Primary Face Was Previously Needed

Before Iteration 9, the system relied on a single "primary face" (the
largest detected face by bounding box area) as the subject-of-interest:

1. **EventManager compatibility** — The single-entity `EventManager` (Iteration 3)
   accepts one `Observation` per frame.  Primary face was the only face that
   produced an Observation.

2. **Deterministic subject selection** — With one face feeding the event system,
   logs and events were predictable and non-flickering.

3. **Anti-flicker stability** — Choosing the largest face prevented the system
   from oscillating between different people across frames.

4. **Iterative migration** — Primary face acted as a safe bridge while the ML
   pipeline expanded from single-face to multi-face (Iterations 7 and 8).

---

## What Changed in Iteration 9

### Data Flow (Before)

```
FrameResult → build ONE Observation (from primary face)
            → EventManager.update(obs) → Event | None
```

### Data Flow (After)

```
FrameResult → build List[Observation] (one per detected face)
            → MultiEntityEventManager.update(observations) → List[Event]
```

### The MultiEntityEventManager

A new orchestrator (`app/core/multi_event_manager.py`) that:

- Owns a `Dict[track_key, EventManager]` internally
- Associates observations to tracked entities using **nearest-centroid** heuristic
- Routes each observation to its corresponding per-face `EventManager`
- Creates new `EventManager` instances for genuinely new faces
- Sends "absent" observations to tracks with no matching detection
- Prunes stale tracks that haven't been seen for `lost_frames + 5` frames
- Returns `List[Event]` — zero or more events per frame

### The EventManager Is Unchanged

`app/core/event_manager.py` was **not modified**.  It is the proven,
23-test-covered, single-entity state machine from Iteration 3.  The
orchestrator wraps it — it does not replace or extend it.

---

## Is Primary Face Still Required?

**No — it is now optional.**

| Aspect | Before (It 3–8) | After (It 9) |
|--------|-----------------|-------------|
| Event triggering | Only primary face | Every face independently |
| Observation building | One from primary | One per face |
| EventManager | Single instance | One per tracked entity |
| Preview green box | Structural dependency | UI-only visual hint |
| `primary_detection` | Mandatory for events | Optional — only for preview |
| `result.recognition` | Required by event flow | Kept for backward compat |

Primary face remains as a **soft visual annotation** (green box in preview)
but is no longer a structural dependency for event handling.

---

## Face Association Strategy

### Nearest-Centroid (Current — Weak)

Each tracked entity stores its last known bounding box centroid.  New
detections are matched to the closest existing track within
`MULTI_FACE_ASSOCIATION_DISTANCE` pixels (default: 150px, configurable
via `SV_MULTI_FACE_ASSOCIATION_DISTANCE`).

### Known Limitations

> **WARNING: Centroid-only association is fragile without real tracking.**

- Two people crossing paths will swap identities
- Fast-moving faces may lose association temporarily
- Static or slow-moving faces work reliably
- Identity "jumps" are contained by the per-face cooldown period

### Future Improvement Path

Integration with Iteration 6 tracking (CSRT/KCF) would replace
centroid association with visual feature-based tracking, solving the
identity swap problem.

---

## Configuration

```env
SV_MULTI_FACE_ASSOCIATION_DISTANCE=150.0   # Max centroid distance (px)
SV_MULTI_FACE_MAX_ENTITIES=10              # Max concurrent tracked faces
```

---

## Test Coverage

15 tests in `tests/test_multi_event_manager.py`:

| Test | Aspect |
|------|--------|
| Single-face lifecycle | Backward compat with old system |
| Two independent faces | Independent events per person |
| Association by centroid | Spatial continuity |
| Far detection → new track | Correct track creation |
| Close detection → reuse | No spurious track creation |
| Stale track pruning | Cleanup after disappearance |
| Active track not pruned | No false cleanup |
| No duplicate events | Per-face K-of-N confirmation |
| Cooldown prevents refire | Per-face cooldown |
| Max entities | Resource cap |
| Unknown → unauthorised | Correct event status |
| Mixed known/unknown | Independent per-face status |
| Track key assignment | Correctly tagged observations |
| Event structure | Standard Event fields |
| Euclidean helper | Geometry sanity |

---

## What Remains for Future Work

1. **Visual tracking integration** — Replace centroid association with CSRT/KCF
2. **Multi-entity dashboard** — Show per-person event history
3. **Per-face DB person_id resolution** — Currently `None` for all faces
4. **Multi-face alert service** — Independent alerts per tracked entity
5. **Event deduplication across tracks** — If person A is tracked as both
   `face_0` and `face_3` due to association failure, events may duplicate
