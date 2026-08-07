# SPEC-077: AR Art Placement Preview -- Forge Template Entry

**Status:** DRAFT
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-08-03
**Complements:** SPEC-067 (Forge Wizard)
**Tier:** Operational
**Priority:** HIGH -- required for ADT demo video

**Intent:** Add a pre-canned template to the Forge Wizard's `FORGE_TEMPLATES` catalog so an operator can, in one click, forge a working AR-based interior-design helper: a phone-based app that lets people preview an art piece (painting, framed print, vase, statuette) in their home before buying, by pointing their phone camera at a printed paper fiducial marker placed where the piece would go. The template payload is engineered for FIRST-TRY forge success -- it is the visible demonstration that ADT governance can steer an AI worker to build a complex, camera-facing, sensor-fused application without hallucination or false starts.

**Triggering Event:** CEV-OP-2026-08-03 -- operator preparing an ADT demo video needs (a) a template whose output is visually striking on camera (real-world AR overlay), (b) an intuitively graspable problem statement for a non-technical audience, and (c) a payload so precisely worded that the Architect worker produces a coherent SPEC-001 + child spec tree on the first run, because a failed forge on-camera invalidates the demo's thesis.

**Success Condition:**
1. A new entry appears in the Forge Wizard's "Load template" dropdown labelled `🖼️ AR Art Placement Preview`.
2. Selecting it pre-fills the Screen-1 wish textarea and stashes the Screen-2 fields (users / success / out / constraints) into `forgeData`.
3. Pressing Forge Application spawns the Architect worker which, within the SPEC-067 §5 SLA (~90s), writes a filled `SPEC-001_VISION.md` and 5-7 child specs matching the AR / marker / sensor-fusion / rendering domain (see §3).
4. Decomposing any child spec yields technical tasks (e.g. "integrate MindAR Image target loader") rather than meta tasks.

---

## 1. Template Payload

Insert the following object into the `FORGE_TEMPLATES` array literal in `adt-console/src/js/launcher.js` (currently line 516). Recommended position: immediately after the EyeToy entry (~line 525) since both are camera-vision demos and the visual thematic grouping helps operator navigation.

```js
{
  label: "🖼️ AR Art Placement Preview",
  slug: "ar_art_preview",
  wish: `A mobile-first web app that lets people preview art pieces (paintings, framed prints, vases, statuettes) in their own home before buying. The user prints a paper fiducial marker provided by the app, places it on a wall or shelf where a piece would go, and points their phone camera at the marker. The app renders the digitised art piece anchored to the marker at correct real-world scale so the user can walk around and see how the piece fits -- scale, style, perspective.

Critically, tracking must be robust and stable. The marker is designed to be detected from a distance and at varied angles (a multi-fiducial board or natural-feature-tracking target, not a single fragile square that only works head-on). Once the marker is initially locked, the app fuses camera-based tracking with the phone's gyroscope: if the camera briefly loses sight of the marker, the rendered piece stays put where it was placed rather than jumping, flickering, or disappearing. The user can turn the phone or briefly step away and the art remains anchored to the real wall; when the marker re-enters view, the pose snaps back smoothly rather than teleporting.

Art is represented either as a textured plane derived from a single photo (paintings / framed prints with real-world dimensions supplied by the user in centimetres) or from a supplied 3D model file (GLB / OBJ, for vases and statuettes). The catalog ships with 3 sample pieces -- one painting, one vase, one statuette -- so the demo works immediately out of the box. Users can add their own by uploading a photo plus dimensions, or a GLB file.`,
  users: "Homeowners and interior-design-curious shoppers who want to visualise an art piece in their space before purchasing. Also small gallery / independent-artisan sellers who want to give buyers a low-effort preview tool without building a native app.",
  success: "User loads the app on their phone over HTTPS, picks a sample painting from the catalog, prints (or displays on a second screen) the bundled fiducial marker at its intended real-world size, points the camera at the marker, and sees a correctly-scaled rendering appear anchored to the wall -- a 60cm-wide painting appears ~60cm wide relative to the marker. The user then walks around, turns the phone at moderate angles, or briefly points away from the marker, and the piece remains rock-steady in its placed position (no flicker, no jump, no drift beyond a small centimetre-scale nudge on re-acquisition). A printable marker PDF at a known real-world size is bundled with the app as a first-class deliverable.",
  out: "No AR-headset support in v1 -- phone only. No photorealistic lighting or shadow estimation. No purchase / checkout flow. No account system. No photogrammetry pipeline: users supply either a photo + dimensions or a GLB, they do not scan real objects. No markerless (SLAM-only) tracking in v1 -- the marker is the authoritative anchor. No GPS-based positioning in v1 -- GPS accuracy (5-10 m outdoor, 20-50 m or no lock indoors) is 100-1000x coarser than the cm-scale anchor precision this indoor use case requires; fusing it in would destabilise, not stabilise, the pose. GPS is captured as a v2 open question for a possible outdoor-sculpture-placement mode. No extended translational dead-reckoning beyond the multi-sensor stability window described in constraints.",
  constraints: "Browser-based. Must run on modern iOS Safari and Android Chrome using getUserMedia plus a marker-tracking library that supports iOS Safari without WebXR -- recommended: MindAR (Image / Multi-Target mode) or AR.js NFT (natural-feature tracking). The child spec owning tracking picks the exact library, but the pick MUST work on iOS Safari. No native app, no App Store. Must be served over HTTPS in both dev and production (bundled self-signed cert or a documented mkcert / ngrok flow) -- mobile browsers refuse camera access otherwise. The marker asset is a printable PDF bundled with the app at a fixed known real-world size (recommend A4 portrait with the pattern occupying a known cm-square). Real-world scale MUST be honoured -- rendered dimensions derive from the marker's known physical size, not from arbitrary Three.js units. Tracking must be a fused multi-sensor pipeline (VIO-lite). Primary anchor is the marker via camera; when the marker is in view, all other sensors are calibrated against it. When the marker leaves view: (a) rotation is maintained by gyroscope (DeviceOrientationEvent, ~100 Hz) with heading drift corrected by magnetometer (`webkitCompassHeading` on iOS, `absolute:true` DeviceOrientationEvent on Android); (b) translation is maintained by lightweight optical flow tracking non-marker features on the wall / floor (OpenCV.js feature tracker or equivalent lightweight JS implementation); (c) accelerometer double-integration (DeviceMotionEvent) bridges the first ~1 second while optical flow initialises. Combined, the piece must remain rock-steady for at least 8-10 seconds of marker-off-camera before drift becomes visible. On marker re-acquisition, smooth the pose delta over 200-500 ms -- no visible jump. Progressive enhancement: if `navigator.xr` with WebXR Hit Test is available (Android Chrome), use it as the primary translation source in place of optical flow for indefinite anchor stability; iOS transparently falls back to the multi-sensor stack. Explicitly do NOT use GPS -- see out-of-scope. Fully static / offline-capable -- no server-side AR processing; all art assets and marker PDFs served as static files."
}
```

## 2. Field Rationale (why each field is written the way it is)

| Field | Design decision | Why it matters for first-try success |
|---|---|---|
| `label` | Framed-picture emoji + short human name. | Instantly recognisable in the dropdown; distinguishes from the other camera-vision template (EyeToy). |
| `slug` | `ar_art_preview` -- lowercase snake. | Joins the existing slug convention (`pixel_art`, `budget_tracker`); yields a clean project dir. |
| `wish` (para 1) | Concrete problem statement in one paragraph. | Gives the Architect worker enough to fill SPEC-001 §1 Problem + §2 Vision without inventing filler. |
| `wish` (para 2) | Elevates tracking stability + gyroscope fusion to a first-class requirement, in prose. | Without this, the worker naively picks a fragile single-fiducial approach; adding it here forces an explicit tracking-robustness child spec. |
| `wish` (para 3) | Two asset paths (textured plane from photo, GLB for 3D) + explicit shipped-catalog count. | Prevents the classic "TODO: add sample assets" outcome; the shipped 3-piece catalog is required for the demo to visually work. |
| `users` | Two audience segments (buyer + seller). | Yields a natural SPEC-001 §3 Users bullet list without prompting. |
| `success` | Single observable end-to-end sentence with the scale check and stability check baked in. | Matches SPEC-067 §3 "observable test" contract; the scale + stability clauses are the parts most likely to look broken on camera, so we restate them. |
| `out` | Explicitly rules out: headsets, lighting sim, checkout, accounts, photogrammetry, markerless SLAM, extended dead-reckoning. | Each of these is a rabbit-hole the Architect would otherwise scope in and blow the demo timeline. |
| `constraints` | Names candidate libraries (MindAR, AR.js NFT), locks HTTPS, locks marker as printable PDF at known size, hard-requires scale honouring, specifies the full VIO-lite fusion stack (camera + gyro + magnetometer + optical flow + accelerometer bridging, with WebXR-on-Android as opportunistic enhancement), fixes stability budget at 8-10 seconds, explicitly forbids GPS with reason. | These are the specifically named landmines that make browser-AR demos fail on stage. Each one names the problem AND names the mitigation, so the worker doesn't need to research. Naming the fusion stack precisely (rather than "use sensors") prevents the naive gyro-only implementation that would look janky on camera. |
| `out` (GPS clause) | Rejects GPS in v1 with an explicit numeric-precision reason. | Two purposes: (1) prevents the forge worker from wiring up geolocation on its own initiative; (2) creates a visible-on-camera moment during the demo where the generated SPEC-001 §7 defers GPS with governance-grade reasoning -- exactly what the framework's value story needs. |

## 3. Expected Architect-Worker Output (informational)

When the SPEC-067 Phase A + B Architect worker runs on this template, the following child spec split is anticipated. Reviewers should compare the actual forge output against this list to detect drift.

* **SPEC-001 VISION** -- filled per SPEC-067 §3 Phase A.
* **SPEC-002** Camera Access + Video Pipeline -- `getUserMedia`, iOS Safari orientation quirks, HTTPS requirement + local-dev cert flow.
* **SPEC-003** Marker Design + Detection -- multi-fiducial board or NFT target for range / angle robustness; printable PDF asset at known real-world size.
* **SPEC-004** Multi-Sensor Pose Fusion (VIO-lite) -- world-transform caching on marker lock; on marker loss, fused pose from gyroscope + magnetometer (rotation with drift correction) + optical flow feature tracking (translation) + accelerometer double-integration (~1 s bridging); smoothed re-acquisition over 200-500 ms. Progressive-enhancement branch for Android Chrome using WebXR Hit Test as primary translation source. Explicit non-goal: GPS integration. NEW spec category driven by the operator's stability requirement.
* **SPEC-005** Asset Pipeline + Real-World Scale -- photo → textured plane (dimensions in cm), GLB / OBJ loader, marker-anchored scale derivation.
* **SPEC-006** Rendering Layer -- Three.js scene graph, marker-parent transform, camera intrinsics.
* **SPEC-007** Catalog UI + Sample Assets + Marker PDF -- grid picker, 3 shipped samples (painting / vase / statuette), user-upload flow, bundled marker download.

Child count: **6-7** (upper end of SPEC-067 §8 range of 3-7). This upper-bound sit is intentional -- the Spec Map that operators see in the demo video should look substantive, not sparse.

Anticipated SPEC-001 §7 Open Questions the worker should raise (useful signal that the worker read the prompt carefully):
- Marker size (A4 portrait vs credit-card vs custom cm-square)?
- Sample-art licensing source (public-domain museum APIs vs commissioned)?
- Default phone orientation (landscape vs portrait) for the AR view?
- Multi-fiducial board vs NFT -- which does the tracking child spec pick?
- Outdoor v2 mode: for garden sculptures / building-scale murals where marker printing is impractical, could GPS + compass + WebXR anchors extend the app? (v2 direction; explicitly not in v1 per §out.)
- OpenCV.js is ~8 MB; is a lighter hand-rolled Lucas-Kanade tracker acceptable for the optical-flow child spec?

## 4. Affected Paths

| Path | Role | Change |
|---|---|---|
| `adt-console/src/js/launcher.js` | Frontend | Insert the §1 payload into `FORGE_TEMPLATES` after the EyeToy entry (~line 525). Single array-literal addition, no logic change. |
| `_cortex/specs/SPEC-077_AR_ART_PREVIEW_FORGE_TEMPLATE.md` | Architect | This file. |

## 5. Rollout

Single edit, single downstream role (Frontend). No backend, no config, no ADS-schema change.

1. Frontend_Engineer opens `adt-console/src/js/launcher.js`, inserts the payload from §1.
2. Rebuild ADT Console (Tauri) or hard-refresh if running the dev bundle.
3. Smoke test: open Forge Wizard → "Load template" dropdown shows `🖼️ AR Art Placement Preview` → selecting it fills wish + path + name → Screen 2 shows pre-filled users / success / out / constraints → pressing Forge produces a project with SPEC-001 + 6-7 children matching §3.

ETA: ~15 minutes including smoke test.

## 6. Acceptance Criteria

* ✅ Template appears in dropdown with the specified label.
* ✅ Selecting it pre-fills all 7 wizard fields (wish, path, name derived; users / success / out / constraints stashed in `forgeData`).
* ✅ Forge run against this template produces a filled SPEC-001 (no `TODO:` strings) whose §5 Success Criteria matches or paraphrases the template's `success` field including the stability clause.
* ✅ 5-7 child specs are created, at least one explicitly names marker tracking, at least one explicitly names multi-sensor pose fusion (gyroscope + magnetometer + optical flow at minimum), and at least one explicitly names real-world scale from marker size.
* ✅ Decomposing any child produces technical tasks (not meta tasks like "write Problem section").
* ✅ Anticipated Open Questions (§3 last block) show up in SPEC-001 §7 at least in paraphrased form -- including the GPS-for-outdoor-v2 deferral, which is the visible-on-camera governance moment.
* ✅ Neither SPEC-001 nor any child spec proposes GPS as a v1 sensor -- if the worker adds GPS despite the explicit `out` clause, that is a governance failure the demo would not want to show.

## 7. Cross-Spec Impact

* **SPEC-067 (Forge Wizard):** additive only -- new entry in the `FORGE_TEMPLATES` array; no schema, endpoint, or prompt-template change.
* **SPEC-043 (Forge):** unaffected -- API contract unchanged.
* **SPEC-062-F (Verification):** the child specs produced will each carry `acceptance_criteria` placeholders as normal.

## 8. Out of Scope (this spec)

* Actually implementing the AR app itself -- that is the forge worker's job downstream from this template.
* Choosing the specific tracking library (MindAR vs AR.js NFT) -- deferred to SPEC-003 in the forged project.
* Producing sample art assets or the marker PDF -- deferred to SPEC-003 / SPEC-007 in the forged project.
* Any change to the Forge Wizard UI beyond adding this dropdown entry.
* Backporting the gyroscope-fallback pattern into other templates (would be a separate spec).

---

*"A demo is a promise the framework keeps in front of a camera. The prompt is the promise."*
