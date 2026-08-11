# Cross-Shot Continuity Checklist

Use this checklist to validate Visual DNA consistency across all clips before generation. This is **in addition to** single-prompt validation from the standard `veo` skill.

---

## Validation Process

1. **First**: Validate each prompt individually using `veo/validation/prompt-checklist.md`
2. **Then**: Validate cross-shot continuity using this checklist
3. **Both must pass** before presenting to user

---

## CRITICAL: Visual DNA Consistency

These elements MUST match across ALL prompts. Extract and compare.

### Color Palette Consistency

**Check**: Do all prompts describe the same color palette?

| What to Look For | Pass | Fail |
|------------------|------|------|
| Primary color mentioned | "cool blue" in all | "cool blue" in some, "warm gold" in others |
| Secondary color consistent | "warm neutral" in all | Different secondary colors |
| Accent color consistent | "amber accent" in all | Switching between accents |
| Shadow treatment consistent | "lifted blacks" in all | "crushed blacks" vs "lifted blacks" |

**Extraction Template**:
```
Shot 1: [extracted color descriptors]
Shot 2: [extracted color descriptors]
Shot 3: [extracted color descriptors]
Shot 4: [extracted color descriptors]

Match? [ ] YES  [ ] NO - Fix before proceeding
```

**Common Issues**:
- Forgetting to include palette in one prompt
- Switching accent colors mid-sequence
- Inconsistent shadow/highlight treatment

---

### Lighting Style Consistency

**Check**: Do all prompts describe compatible lighting?

| What to Look For | Pass | Fail |
|------------------|------|------|
| Light quality consistent | "soft diffused" in all | "soft" in some, "hard" in others |
| Light direction compatible | Same general direction | Conflicting directions |
| Contrast level consistent | Same contrast approach | Dramatic vs flat mixing |
| Atmosphere consistent | "atmospheric haze" in all or none | Inconsistent haze |

**Extraction Template**:
```
Shot 1: [extracted lighting descriptors]
Shot 2: [extracted lighting descriptors]
Shot 3: [extracted lighting descriptors]
Shot 4: [extracted lighting descriptors]

Match? [ ] YES  [ ] NO - Fix before proceeding
```

**Common Issues**:
- Mixing hard and soft lighting (creates visual jarring)
- Inconsistent contrast (premium luxury vs flat corporate)
- Adding/removing atmosphere between shots

---

### Atmosphere/Mood Consistency

**Check**: Do all prompts evoke the same emotional space?

| What to Look For | Pass | Fail |
|------------------|------|------|
| Overall mood consistent | "ethereal" throughout | "ethereal" then "industrial" |
| Energy level consistent | Same baseline energy | Calm then frantic |
| Style reference consistent | Same reference or none | Different film references |
| Texture approach consistent | Similar texture treatment | Clean vs gritty mixing |

**Extraction Template**:
```
Shot 1: [extracted mood/atmosphere descriptors]
Shot 2: [extracted mood/atmosphere descriptors]
Shot 3: [extracted mood/atmosphere descriptors]
Shot 4: [extracted mood/atmosphere descriptors]

Match? [ ] YES  [ ] NO - Fix before proceeding
```

**Common Issues**:
- Mood drift over multiple prompts
- Conflicting style references
- Inconsistent texture (clinical vs organic)

---

### Camera Energy Consistency

**Check**: Is camera energy appropriate and progressive?

| What to Look For | Pass | Fail |
|------------------|------|------|
| Baseline energy established | Consistent pace words | Erratic pace changes |
| Movement descriptors compatible | Similar intensity | "slow" then "fast" then "slow" |
| Progression appropriate | Gradual build okay | Random energy spikes |

**Extraction Template**:
```
Shot 1: [movement] at [pace]
Shot 2: [movement] at [pace]
Shot 3: [movement] at [pace]
Shot 4: [movement] at [pace]

Progression logical? [ ] YES  [ ] NO - Fix before proceeding
```

**Acceptable Energy Progressions**:
- Steady throughout (contemplative content)
- Gradual increase (building to climax)
- Peak in middle, resolve (dramatic structure)

**Unacceptable Energy Progressions**:
- Random spikes and drops
- Dramatic decrease (loses momentum)
- Jarring shifts between adjacent shots

---

## Adjacent Shot Transitions

Check that adjacent shots will cut together well.

### Shot-to-Shot Compatibility

For each pair of adjacent shots, verify:

| Check | What to Look For |
|-------|------------------|
| Camera direction compatible | Movement directions don't conflict |
| Energy level compatible | No jarring pace change |
| Subject scale compatible | Not too extreme a jump |
| Conceptual continuity | Narrative makes sense |

**Template**:
```
Shot 1 → Shot 2:
  Camera direction compatible? [ ]
  Energy compatible? [ ]
  Scale jump reasonable? [ ]
  Conceptual continuity? [ ]

Shot 2 → Shot 3:
  [repeat checks]

Shot 3 → Shot 4:
  [repeat checks]
```

### Problematic Transitions

**AVOID these adjacent shot patterns:**

| Pattern | Problem | Fix |
|---------|---------|-----|
| Dolly forward → Dolly forward | Repetitive, no variation | Change one to orbit or static |
| Fast → Slow → Fast | Energy whiplash | Smooth the progression |
| Macro → Wide → Macro | Jarring scale jumps | Insert medium shot |
| Opposite directions | Disorienting | Match or contrast intentionally |

---

## Quick Continuity Check

Use this rapid checklist for all multi-shot projects:

```
VISUAL DNA MATCH CHECK
══════════════════════════════════════

Project: ________________
Number of shots: ____

□ Color Palette
  Extracted: _______________________
  Consistent across all prompts? [ ]

□ Lighting Style
  Extracted: _______________________
  Consistent across all prompts? [ ]

□ Atmosphere/Mood
  Extracted: _______________________
  Consistent across all prompts? [ ]

□ Camera Energy
  Baseline: _______________________
  Progression logical? [ ]

TRANSITION CHECKS
═════════════════

□ Shot 1 → 2: Compatible [ ]
□ Shot 2 → 3: Compatible [ ]
□ Shot 3 → 4: Compatible [ ]
[Add more as needed]

RESULT
══════
□ ALL CHECKS PASSED → Ready for generation
□ ISSUES FOUND → Fix before proceeding:
  _________________________________
  _________________________________
```

---

## Validation Output Format

When presenting validation to user, format as:

**PASSED:**
```
Cross-Shot Continuity: PASSED

Visual DNA Consistency:
  - Color palette: "cool blue with amber accents" ✓ (all 4 shots)
  - Lighting: "soft diffused with rim" ✓ (all 4 shots)
  - Atmosphere: "ethereal tech" ✓ (all 4 shots)
  - Camera energy: measured, gradual build ✓

Transitions:
  - Shot 1→2: dolly → push ✓
  - Shot 2→3: push → orbit ✓
  - Shot 3→4: orbit → pull ✓
```

**FAILED:**
```
Cross-Shot Continuity: ISSUES FOUND

Visual DNA Inconsistencies:
  ✗ Lighting mismatch:
    - Shots 1, 2, 4: "soft diffused"
    - Shot 3: "hard directional" ← FIX THIS
    Suggested fix: Change Shot 3 to "soft diffused with subtle directional accent"

  ✗ Camera energy spike:
    - Shots 1, 2: "slow"
    - Shot 3: "fast dynamic" ← FIX THIS
    - Shot 4: "slow"
    Suggested fix: Change Shot 3 to "moderate, smooth"

Corrected prompts provided below.
```

---

## Common Multi-Shot Mistakes

### Mistake 1: Copy-Paste Drift
**What happens**: When adapting prompts, Visual DNA descriptors get slightly modified each time.
**Fix**: Copy exact Visual DNA phrases, don't paraphrase.

### Mistake 2: Shot 1 Syndrome
**What happens**: First shot is crafted carefully, later shots get less attention.
**Fix**: Give equal attention to all shots. Validate systematically.

### Mistake 3: Overcorrection
**What happens**: Trying to add "variety" by changing visual treatment per shot.
**Fix**: Variety comes from subject/camera, NOT from Visual DNA.

### Mistake 4: Narrative Over Visuals
**What happens**: Focus on story beats, forget visual consistency.
**Fix**: Story structure and Visual DNA are both mandatory.

---

## Visual DNA Enforcement Phrases

Keep these exact phrases consistent across prompts:

**Tech/SaaS**:
- "cool blue palette with warm amber accents"
- "soft diffused lighting with subtle rim separation"
- "ethereal tech atmosphere"

**Luxury/Premium**:
- "deep rich blacks with warm gold accents"
- "hard directional lighting with high contrast"
- "exclusive premium atmosphere"

**Corporate**:
- "professional blue palette with [accent] highlights"
- "soft diffused professional lighting"
- "professional atmosphere"

Modify the subject, camera, and action—but keep these phrases verbatim.
