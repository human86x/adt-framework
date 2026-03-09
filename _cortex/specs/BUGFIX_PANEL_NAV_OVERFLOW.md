# BUGFIX: ADT Panel Navigation Bar Overflow

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-03-08
**Priority:** MEDIUM
**Assigned To:** Frontend_Engineer
**Spec Ref:** SPEC-015 (ADT Operational Center)

---

## Problem

The ADT Panel top navigation bar has 10 items plus the brand. On screens narrower than ~1400px, the nav items wrap or stretch beyond the viewport, breaking the layout. The nav currently uses `navbar-expand-lg` (collapses at <992px) but even at 992-1400px the items overflow.

**Affected file:** `adt_center/templates/base.html` (lines 14-76)
**Affected CSS:** `adt_center/static/css/adt.css` (lines 43-61)

## Root Cause

- 10 nav links + brand + SCR badge = too many items for a single horizontal row
- `.nav-link` padding is `0.5rem 0.75rem` -- generous for this many items
- No `flex-wrap` prevention or overflow handling
- `navbar-expand-lg` breakpoint (992px) is too low for 10 items

## Required Fix

Apply ALL of the following changes:

### 1. Reduce nav link padding (adt.css)

Change `.navbar-adt .nav-link` padding from `0.75rem` to `0.5rem`:

```css
/* BEFORE */
.navbar-adt .nav-link {
    padding: 0.5rem 0.75rem !important;
}

/* AFTER */
.navbar-adt .nav-link {
    padding: 0.4rem 0.5rem !important;
    white-space: nowrap;
}
```

### 2. Reduce nav link font size slightly (adt.css)

```css
/* BEFORE */
.navbar-adt .nav-link {
    font-size: 0.875rem;
}

/* AFTER */
.navbar-adt .nav-link {
    font-size: 0.8125rem;
}
```

### 3. Reduce nav-icon margin (adt.css)

```css
/* BEFORE */
.navbar-adt .nav-link .nav-icon {
    margin-right: 0.35rem;
}

/* AFTER */
.navbar-adt .nav-link .nav-icon {
    margin-right: 0.2rem;
}
```

### 4. Change breakpoint from lg to xl (base.html)

On line 14, change `navbar-expand-lg` to `navbar-expand-xl` so the hamburger menu activates at <1200px instead of <992px:

```html
<!-- BEFORE -->
<nav class="navbar navbar-expand-lg navbar-adt sticky-top">

<!-- AFTER -->
<nav class="navbar navbar-expand-xl navbar-adt sticky-top">
```

Also update the toggler target stays consistent (it already uses `id="navMain"` so no change needed there).

### 5. Add overflow safety (adt.css)

Add a new rule to prevent the nav from ever pushing beyond viewport:

```css
.navbar-adt .navbar-nav {
    flex-wrap: nowrap;
    overflow-x: auto;
    -ms-overflow-style: none;
    scrollbar-width: none;
}
.navbar-adt .navbar-nav::-webkit-scrollbar {
    display: none;
}
```

This allows horizontal scrolling as a last resort on very narrow wide-screens, with the scrollbar hidden.

### 6. Hide nav-icon text on mid-size screens (adt.css)

Add a responsive rule that hides the icon characters on tight screens so only text shows:

```css
@media (min-width: 1200px) and (max-width: 1439px) {
    .navbar-adt .nav-link .nav-icon {
        display: none;
    }
}
```

## Verification

After applying:
1. At 1920px+: All 10 items visible with icons, no overflow
2. At 1200-1439px: All 10 items visible without icons, no overflow
3. At <1200px: Hamburger menu collapses all items
4. The Governance SCR badge counter must remain visible and correctly positioned

## Files to Edit

| File | Lines | Change |
|------|-------|--------|
| `adt_center/static/css/adt.css` | 43-61 | Padding, font-size, margin, overflow, responsive rules |
| `adt_center/templates/base.html` | 14 | `navbar-expand-lg` -> `navbar-expand-xl` |
