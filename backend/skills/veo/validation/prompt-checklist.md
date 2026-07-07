# Prompt Quality Checklist

Use this checklist before presenting any prompt to the user. Validation is mandatory—never skip it.

---

## REJECT (Do Not Generate)

These issues will cause poor results or wasted API calls. Fix before proceeding.

### Multiple Camera Movements
**Pattern**: Stacking movements like "dolly while panning", "orbit and zoom", "tracking with tilt"

**Why it fails**: Veo interprets stacked movements unpredictably—usually favoring one and ignoring others, or creating jarring motion.

**Fix**: Choose ONE movement. Ask: "What's the primary visual journey?"

| Bad | Good |
|-----|------|
| "dolly forward while panning right" | "slow dolly forward" |
| "orbit with crane up" | "slow orbit" |
| "tracking shot with zoom" | "tracking left" |

---

### Text or UI Element Requests
**Pattern**: "show the logo", "text saying...", "display the tagline", "UI overlay"

**Why it fails**: Veo cannot render readable text. Results are illegible or distorted.

**Fix**: Remove text requests entirely. Add text in post-production.

| Bad | Good |
|-----|------|
| "floating text saying 'Welcome'" | "floating luminous particles" |
| "logo appearing on screen" | "geometric form materializing" |
| "dashboard UI elements" | "abstract data visualization shapes" |

---

### Conflicting Descriptors
**Pattern**: Opposing adjectives that create ambiguous direction

**Why it fails**: The model cannot reconcile contradictions—output becomes generic.

**Fix**: Commit to ONE direction.

| Bad | Good |
|-----|------|
| "dynamic but subtle" | "subtle" OR "dynamic" |
| "energetic but calm" | "contemplative with gentle energy" |
| "minimal yet complex" | "minimal, refined" |
| "fast-moving but relaxed" | "flowing, unhurried" |

---

### Overcomplicated Scenes
**Pattern**: Multiple subjects, multiple simultaneous actions, complex narratives

**Why it fails**: Veo has limited scene coherence for complex staging. Results become chaotic.

**Fix**: One subject, one action, one focus.

| Bad | Good |
|-----|------|
| "two people talking while a car passes and birds fly overhead" | "close-up of hands gesturing during conversation" |
| "particles, geometric shapes, and liquid metal all moving" | "liquid metal surface slowly morphing" |

---

## WARNING (Suggest Improvements)

These won't necessarily fail, but will likely produce generic/forgettable results.

### Generic Descriptions (Lacking Material Specificity)
**Pattern**: Vague nouns without texture, material, or specific detail

**Impact**: Output becomes generic stock footage.

**Fix**: Add material specificity, texture detail, or unique characteristics.

| Generic | Specific |
|---------|----------|
| "metal surface" | "brushed titanium with microscopic scratches catching light" |
| "water" | "black coffee rippling in a ceramic cup" |
| "particles" | "bioluminescent spores drifting upward" |
| "light" | "single hard beam cutting through particulate atmosphere" |
| "nature" | "Pacific Northwest forest floor, post-rain, fern-heavy" |

---

### Missing Lighting/Atmosphere Direction
**Pattern**: No mention of light quality, direction, or atmospheric conditions

**Impact**: Model uses default/random lighting—inconsistent with intended mood.

**Fix**: Add explicit lighting direction.

**Lighting elements to include:**
- Light quality: `hard`, `soft`, `diffused`, `specular`
- Light direction: `backlit`, `side lit`, `top light`, `rim light`
- Time reference: `golden hour`, `blue hour`, `overcast`, `night`
- Atmosphere: `fog`, `mist`, `dust motes`, `haze`

---

### Duration Mismatch
**Pattern**: Content complexity doesn't match selected duration

**Impact**: Rushed or overly sparse video.

| Content Type | Recommended Duration |
|--------------|---------------------|
| Simple loop, single element | 4s |
| Scene with environmental detail | 6s |
| Product reveal, multiple beats | 8s |
| Hero background | 4s (smoothest loop) |

---

### Missing Color Direction
**Pattern**: No palette, temperature, or grade guidance

**Impact**: Model defaults to generic color treatment.

**Fix**: Add one of:
- Temperature: `warm`, `cool`, `neutral`
- Palette: `monochromatic blue`, `earth tones`, `high contrast`
- Grade reference: `desaturated`, `lifted blacks`, `crushed shadows`
- Film reference: `Fincher desaturated`, `Malick golden`

---

## LOOP-SPECIFIC (Hero Backgrounds)

For any hero background or ambient loop use case, verify ALL of these:

### Required Flags
- [ ] **Contains "seamless loop"** — Signals loop intent to model
- [ ] **Contains "locked camera" or "static camera"** — Prevents jarring motion at loop point

### Motion Requirements
- [ ] **Motion described as subtle** — Use: `slowly`, `gently`, `imperceptibly`, `subtle`
- [ ] **No dramatic camera movements** — No dollies, orbits, or tracking for hero use
- [ ] **Single element in motion** — Particles OR fog OR light shift, not all three

### Technical Requirements
- [ ] **Duration 4-6 seconds** — Shorter loops are smoother
- [ ] **720p resolution** — Unless high-bandwidth deployment
- [ ] **Audio disabled** — Hero backgrounds should be silent

### Visual Requirements
- [ ] **Subject survives 35% darkening** — Hero text overlay requires dark tolerance
- [ ] **High-contrast subjects preferred** — Survives compression and dimming
- [ ] **No fine detail dependent content** — Will be lost under text overlay

---

## Quick Validation Flow

```
1. Camera Movement
   [ ] Only ONE movement type?
   [ ] No stacking (while, and, with)?

2. Content
   [ ] No text/UI requests?
   [ ] No conflicting descriptors?
   [ ] Single focused subject?

3. Specificity
   [ ] Material detail present?
   [ ] Lighting direction included?
   [ ] Color palette specified?

4. For Loops Only
   [ ] "seamless loop" present?
   [ ] "locked camera" present?
   [ ] Motion is subtle?
   [ ] Duration 4-6s?

All checks pass → READY FOR REVIEW
Any REJECT issue → Fix before presenting
Any WARNING → Suggest improvement, allow override
```

---

## Validation Output Template

When presenting to user, format validation status:

**PASSED:**
```
Validation: PASSED
- Single camera movement (dolly forward)
- No text requests
- Material specificity present
- Loop flags included
```

**FAILED (with fixes):**
```
Validation: ISSUES FOUND

REJECT:
- Multiple camera movements: "dolly while panning" → Use "slow dolly forward"
- Text request detected: "company logo" → Remove, add in post

WARNING:
- Generic description: "metal surface" → Consider "brushed aluminum with fine texture"

Suggested corrected prompt:
[corrected version]
```
