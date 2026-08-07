# SPEC-079: Camera-Navigated 3D Solar System -- Forge Template Entry

**Status:** DRAFT
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-08-05
**Complements:** SPEC-067 (Forge Wizard), SPEC-077 (AR Art Preview -- sibling template)
**Tier:** Operational
**Priority:** HIGH -- primary asset for ADT demo video (screen-capturable, unlike SPEC-077's phone-recorded AR)

**Intent:** Add a second pre-canned template to the Forge Wizard: an educational 3D solar system rendered in Three.js, navigated by hand movement in front of the webcam (EyeToy pattern). Chosen deliberately as the video's *primary* demo asset because it is fully screen-capturable, needs no phone camera or physical props, and its Launch button in the ADT Console opens a real interactive app the audience can watch immediately. SPEC-077's AR preview remains in the codebase as a secondary "the framework handles harder things too" reference. The template payload is engineered for FIRST-TRY forge success and for a spec/child-tree that will look substantive in the Spec Map on-camera.

**Triggering Event:** 2026-08-05 -- operator strategically pivoted the video's primary demo target from the AR Art Preview (produced by SPEC-077) to a screen-capturable browser app after realising the AR flow required phone recording + composite editing that would distract from the framework's actual message. The solar system reuses the EyeToy webcam-tracking pattern already validated by the EyeToy template, is visually striking, and gives the MRR/standards-recommendation UI a natural moment to shine on-camera (see §Dependencies).

**Success Condition:**
1. A new entry appears in the Forge Wizard's "Load template" dropdown labelled `🪐 Camera-Navigated 3D Solar System`.
2. Selecting it pre-fills the Screen-1 wish textarea and stashes the Screen-2 fields (users / success / out / constraints) into `forgeData`.
3. Pressing Forge Application spawns the Architect worker which, within the SPEC-067 §5 SLA (~90s), writes a filled `SPEC-001_VISION.md` and 5-7 child specs matching the domain split in §3.
4. Decomposing any child spec yields technical tasks.
5. **After child builds complete**, pressing the Console's Launch button opens the running solar system in a browser window; hand movement in front of the webcam pans the camera; clicking a planet triggers a fly-to + fact card.

---

## 1. Template Payload

Insert as a new object into `FORGE_TEMPLATES` in `adt-console/src/js/launcher.js`. Recommended position: immediately after the EyeToy entry (before AR Art Placement Preview) so the two webcam-tracked templates cluster together in the dropdown.

```js
{
  label: "🪐 Camera-Navigated 3D Solar System",
  slug: "solar_system",
  wish: `A browser-based educational 3D visualisation of our solar system that runs entirely offline. The Sun sits at the centre, the 8 major planets orbit at log-compressed but visually pleasing distances, and Earth's Moon orbits Earth. Each planet uses a bundled high-resolution equirectangular texture. Planets rotate on their axes and orbit the Sun at reasonable relative speeds -- not physically accurate to true Kepler mechanics but faithful to relative ordering.

Navigation is by webcam-tracked hand movement, the same pattern as the EyeToy template already in this catalog. The user waves or moves their hand in front of the built-in laptop webcam and the camera pans smoothly through space -- move hand left, camera pans left; move hand up, camera pitches up. A soft on-screen indicator shows where the hand is being tracked. No keyboard, no mouse required for navigation; a mouse click is only needed for planet selection.

Clicking any planet triggers a smooth cinematic fly-to camera transition (~2 seconds) that frames the planet, then opens a fact card displaying real-world data: name, distance from Sun (in km and AU -- real values, not the log-compressed rendered values), diameter, day length, year length, moons, and 2-3 notable facts. Clicking a "Return" button zooms the camera back out to the whole-system view.

The catalog of facts is a hardcoded JSON file bundled with the app -- no NASA API calls, no external dependencies at runtime, works entirely offline.`,
  users: "Students, educators, curious learners, families, and museum-style installations -- anyone who wants an intuitive visual grasp of planetary scale, ordering, and basic facts without installing an app.",
  success: "User opens the app, sees the Sun plus the 8 planets plus Earth's Moon rendered in Three.js with orbital motion. Waving their hand in front of the webcam smoothly pans the camera through space (EyeToy pattern). Clicking Mars triggers a ~2-second fly-to transition; the camera frames Mars and a fact card appears showing distance-from-Sun in km + AU, diameter, day/year length, moon count, and notable facts (all from bundled JSON, no fetch). Clicking Return zooms back out. Works fully offline after first load. Frame rate stays smooth (>=30fps) on a mid-range 2020 laptop.",
  out: "No true-scale physics -- true scaling would make Neptune invisible or the Sun a screen-filling disc. Log-compressed distances are honoured with real numbers shown in the fact card so the education stays honest. No exoplanets. No spacecraft, satellites, or missions. No VR / AR mode. No multi-user, accounts, leaderboards, or progress tracking. No NASA API, no runtime fetches -- all art assets and facts bundled at build time. No audio / ambient soundtrack in v1 (video producer can add in post if desired). No mobile support required for v1 (nice-to-have but not blocking).",
  constraints: "Browser-based single-page app. Rendering: Three.js (bundled or via ES module). Camera navigation: MediaPipe Hands (or equivalent JS hand-tracker) via getUserMedia; same tracking pattern as the EyeToy template already in this codebase -- reuse conventions where possible. Textures: bundled equirectangular JPGs sourced from NASA / JPL / ESO public-domain releases; a NOTICE.md file must credit sources. Facts: hardcoded JSON at src/planet_facts.json -- 8 planets + Sun + Moon + real distances / diameters / day / year lengths / moon counts / 2-3 notable facts per body. Distance scale: log-compressed (e.g. rendered_distance = k1 * log(1 + real_AU * k2)) so Neptune is visible without dwarfing inner planets; document the exact function in a comment. Fact cards display REAL numbers not rendered numbers. Fly-to camera transitions use Three.js quaternion slerp + eased position interpolation, ~2 second duration. Must serve over HTTPS for camera access -- dev flow uses mkcert or a documented self-signed cert setup. Runs on desktop Chrome, Firefox, and Safari (latest). Frame rate target >=30fps on mid-range hardware; if hand-tracking is expensive, run tracker at 15fps and interpolate. Fully offline after first load -- no runtime network calls."

**Note:** Earlier drafts of this payload contained an explicit "aligns with world-wide standards…" clause enumerating WCAG / IAU / Khronos / W3C / etc. This was removed under SPEC-080 which codifies standards inheritance as an intrinsic ADT rule: the MRR classifier's `suggested_rr_ids` are automatically promoted to mandatory `standards_refs[]` on the vision spec and inherited by every child. Template payloads MUST NOT re-state standards concerns; that is framework territory, not operator-input territory. See REQ-123.
}
```

## 2. Field Rationale

| Field | Design decision | Why it matters for first-try success |
|---|---|---|
| `label` | Ringed-planet emoji + short human name. | Recognisable, differentiates from EyeToy and AR Art. |
| `slug` | `solar_system` -- straightforward. | Matches existing slug convention. |
| `wish` (para 1) | Contents locked (Sun + 8 planets + Moon) + log-compressed scale + rotating + orbiting. | Prevents the worker from either (a) including Pluto / dwarf planets and blowing scope, or (b) attempting true-scale and producing an unusable render. |
| `wish` (para 2) | Explicitly ties camera navigation to the EyeToy pattern already in the codebase. | The worker can literally reference the sibling template's approach -- huge win for consistency and lower hallucination risk. |
| `wish` (para 3) | Fly-to + fact card + REAL numbers in fact card. | The fly-to is the cinematic moment for the video; the "real numbers in the card even though rendered scale is compressed" is the educational-integrity safeguard. |
| `users` | Broad but bounded. | Yields a natural §3 Users list; also implies the "museum installation" angle which sanity-checks the offline / no-account requirements. |
| `success` | Single observable end-to-end sentence with frame-rate floor. | Matches SPEC-067 §3 contract; the frame-rate floor is the visually-fragile bit for a demo take. |
| `out` | Explicitly rules out: true scale, exoplanets, VR/AR, accounts, NASA API, audio, mobile. | Each is a rabbit-hole; ruling out mobile is the most controversial but the video is desktop-recorded so mobile support has zero demo value and would double scope. |
| `constraints` | Names Three.js + MediaPipe Hands + bundled equirectangular textures + log-compressed distance function form + HTTPS. | Names every failure-prone landmine of "browser 3D + webcam" and pre-answers each. Reuse EyeToy conventions clause reduces divergence between the two templates. |

## 3. Expected Architect-Worker Output

* **SPEC-001 VISION** -- filled per SPEC-067 §3 Phase A.
* **SPEC-002** Three.js Scene + Orbital Mechanics -- Sun + 8 planets + Moon geometry, log-compressed distances, axial rotation, orbital motion.
* **SPEC-003** Planet Textures + Materials + Lighting -- bundled equirectangular texture pipeline, Sun as emissive, planet material tuning, single directional light + ambient.
* **SPEC-004** Camera Navigation via MediaPipe Hands -- getUserMedia, hand-landmark inference, hand-position → camera-pan mapping, on-screen tracking indicator. Explicit spec to reuse EyeToy tracking conventions where sensible.
* **SPEC-005** Cinematic Fly-To Camera Transitions + Planet Selection -- raycast planet picker, quaternion slerp + eased position interpolation, ~2s duration.
* **SPEC-006** Fact Card UI + Bundled Planet Facts JSON -- fact card component, hardcoded planet_facts.json with real numbers for 10 bodies.
* (optional) **SPEC-007** Application Shell + Onboarding -- HTTPS dev flow, first-run "wave your hand to explore" overlay, NOTICE.md for texture credits.

Child count: **6-7**. This upper-band count is intentional -- the Spec Map that appears in the demo video needs to look substantive.

Anticipated SPEC-001 §7 Open Questions the worker should raise:
- Which specific log-compression function best balances "inner planets visible + Neptune reachable" -- linear-log, sqrt, or empirically-tuned piecewise?
- How to distinguish "hand at edge of frame → keep panning" from "hand at edge → user tired, stop" (dwell threshold vs velocity)?
- Should Saturn's rings ship in v1 despite being outside the strict planets-only contents rule? (Recommended: yes, they read as "the ringed planet" instantly on video.)
- MediaPipe Hands ships as ~10MB of WASM -- acceptable, or use a lighter tracker?

## 4. Affected Paths

| Path | Role | Change |
|---|---|---|
| `adt-console/src/js/launcher.js` | Frontend | Insert §1 payload into `FORGE_TEMPLATES` after the EyeToy entry, before the AR Art Placement Preview entry. |
| `_cortex/specs/SPEC-079_SOLAR_SYSTEM_FORGE_TEMPLATE.md` | Architect | This file. |

## 5. Rollout

Single edit, single downstream role (Frontend). No backend, no config, no ADS-schema change.

1. Frontend_Engineer (or Architect under operator override) inserts §1 payload into launcher.js.
2. Rebuild ADT Console binary.
3. Smoke test: open Forge Wizard → "Load template" dropdown shows `🪐 Camera-Navigated 3D Solar System` → selecting fills all 7 wizard fields → forge produces SPEC-001 + 6-7 children matching §3.

ETA: same batch as SPEC-077's rebuild (~2m 20s Rust incremental build).

## 6. Acceptance Criteria

* ✅ Template appears in dropdown with the specified label.
* ✅ Selecting it pre-fills all 7 wizard fields.
* ✅ Forge run produces a filled SPEC-001 (no `TODO:` strings) whose §5 Success Criteria matches or paraphrases the template's `success` field including the frame-rate floor.
* ✅ 6-7 child specs are created; at least one names Three.js scene / orbital mechanics; at least one names MediaPipe Hands / webcam tracking; at least one names fly-to camera transitions.
* ✅ Decomposing any child produces technical tasks (not meta).
* ✅ At least one Open Question in SPEC-001 §7 mentions the log-compression tradeoff.
* ✅ The word "EyeToy" appears in at least one child spec (either the camera-nav one referencing the sibling template, or the vision itself) -- signal that the worker registered the reuse hint.

## 7. Dependencies for full demo-video value

For MRR-visibility during the forge on-camera (the demo's actual thesis moment), REQ-111 (SPEC-072 intent-matcher silent + `intent_index.json` domain gap) must be resolved first or in parallel. Specifically:

- Backend: unconditional `intent_match_started` / `intent_match_completed` ADS events (fast fix).
- Frontend: Forge Wizard progress screen renders MRR events with suggested standards visible during the ~35s classifier run.
- Config: `intent_index.json` needs a domain bucket that will match on this template's wish -- likely "3d_graphics_educational" or "browser_visualisation" with keywords like solar, planet, three.js, webgl, educational, visualisation.

These fixes are spawned as parallel worker sessions alongside this spec's landing; see the concurrent SPEC-079 rollout notes.

## 8. Cross-Spec Impact

* **SPEC-067 (Forge Wizard):** additive only -- new entry in FORGE_TEMPLATES.
* **SPEC-077 (AR Art Preview):** unaffected; remains in the catalog as a secondary demo asset.
* **SPEC-072 / SPEC-075 (Intent classification):** demo depends on MRR being visible (see §7); does not modify these specs.

## 9. Out of Scope (this spec)

* Implementing the solar-system app itself -- forge worker's job downstream.
* Sourcing / bundling the actual planet textures -- deferred to SPEC-003 in the forged project.
* Choice of specific hand-tracker library beyond "MediaPipe Hands or equivalent" -- deferred to SPEC-004 in the forged project.
* Any change to the Forge Wizard UI beyond the dropdown entry.

---

*"The demo takes a wish and returns a working universe."*
