# Multi-Shot Project Examples

Complete worked examples showing the full workflow from concept to assembled video.

---

## Example 1: SaaS Product Launch Video

**Use Case**: Announcing a new data integration platform feature
**Template**: Product Launch (4 shots)
**Visual DNA**: Tech/SaaS
**Total Duration**: ~26 seconds
**Estimated Cost**: ~$2.00

### Visual DNA Definition

```
VISUAL DNA: DataFlow Pro Feature Launch
=======================================

COLOR PALETTE
  Primary:    Cool blue (#1e3a5f to #3b82f6)
  Secondary:  Slate gray (#64748b)
  Accent:     Warm amber (#f59e0b)
  Shadows:    Lifted blacks, soft depth

LIGHTING STYLE
  Quality:    Soft, diffused
  Direction:  Side-lit with subtle rim separation
  Mood:       Premium tech, not clinical

ATMOSPHERE
  Overall:    Ethereal, innovative, trustworthy
  Texture:    Floating particles, data visualization
  Feel:       Calm confidence

CAMERA ENERGY
  Baseline:   Measured, smooth
  Progression: Gradual build toward reveal
```

### Shot List

| # | Beat | Duration | Camera | Subject | Key Moment |
|---|------|----------|--------|---------|------------|
| 1 | Teaser | 8s | Slow dolly forward | Abstract data environment | Approaching discovery |
| 2 | Reveal | 6s | Push in | Platform visualization | First glimpse |
| 3 | Detail | 6s | Slow orbit | Data flow connections | Capability shown |
| 4 | Context | 6s | Pull out | Ecosystem view | Possibility realized |

### Full Prompts

**Shot 1 - Teaser (8s)**
```
Slow dolly forward through infinite field of abstract data particles,
soft blue nodes floating in void with gentle upward drift,
cool blue palette with warm amber accent highlights,
soft diffused lighting with subtle atmospheric depth,
ethereal tech atmosphere, approaching something significant,
anticipation building
```

**Shot 2 - Reveal (6s)**
```
Smooth push in toward central data hub materializing from particles,
abstract platform form emerging with soft illumination,
cool blue palette with warm amber accents,
soft diffused lighting with rim separation,
ethereal tech atmosphere, first glimpse of innovation,
moment of recognition
```

**Shot 3 - Detail (6s)**
```
Slow orbit around data connection node, intimate view,
light pulses flowing through crystalline pathways,
cool blue palette with amber accent highlights,
soft diffused lighting with subtle rim light,
ethereal tech atmosphere, capability and precision,
premium engineering visible
```

**Shot 4 - Context (6s)**
```
Smooth pull out revealing vast interconnected data ecosystem,
multiple platform nodes working in harmony,
cool blue palette with warm amber success accents,
soft diffused ambient lighting elevated,
ethereal tech atmosphere, expansion and possibility,
confident innovation achieved
```

### Validation Notes

**Single-Prompt Validation**: All PASSED
- Each prompt has single camera movement
- No text/UI requests
- Material specificity present
- Lighting direction clear

**Cross-Shot Continuity**: PASSED
- Color palette: "cool blue palette with warm amber accents" - consistent
- Lighting: "soft diffused lighting" - consistent
- Atmosphere: "ethereal tech atmosphere" - consistent
- Camera energy: measured → measured → measured → measured (consistent)

### Generation Command

```bash
npx ts-node scripts/veo-multi-generate.ts \
  --shots "Slow dolly forward through infinite field of abstract data particles, soft blue nodes floating in void with gentle upward drift, cool blue palette with warm amber accent highlights, soft diffused lighting with subtle atmospheric depth, ethereal tech atmosphere, approaching something significant, anticipation building:::Smooth push in toward central data hub materializing from particles, abstract platform form emerging with soft illumination, cool blue palette with warm amber accents, soft diffused lighting with rim separation, ethereal tech atmosphere, first glimpse of innovation, moment of recognition:::Slow orbit around data connection node, intimate view, light pulses flowing through crystalline pathways, cool blue palette with amber accent highlights, soft diffused lighting with subtle rim light, ethereal tech atmosphere, capability and precision, premium engineering visible:::Smooth pull out revealing vast interconnected data ecosystem, multiple platform nodes working in harmony, cool blue palette with warm amber success accents, soft diffused ambient lighting elevated, ethereal tech atmosphere, expansion and possibility, confident innovation achieved" \
  --durations "8,6,6,6" \
  --output ./output \
  --project-name dataflow-launch \
  --assemble \
  --transition crossfade
```

### Assembly Settings

- **Transition**: Crossfade (0.5s)
- **Total Duration**: ~24.5s (26s minus 1.5s overlap)
- **Post-production**: Add voiceover and music track

---

## Example 2: Luxury Watch Brand Story

**Use Case**: Brand awareness film for luxury timepiece
**Template**: Brand Story (5 shots)
**Visual DNA**: Luxury/Premium
**Total Duration**: ~34 seconds
**Estimated Cost**: ~$2.50

### Visual DNA Definition

```
VISUAL DNA: Heritage Timepiece Brand Story
==========================================

COLOR PALETTE
  Primary:    Deep rich black (#0a0a0a)
  Secondary:  Warm gold (#b8860b)
  Accent:     Cream white (#faf8f5)
  Shadows:    Crushed blacks with detail

LIGHTING STYLE
  Quality:    Hard, directional
  Direction:  Strong key with dramatic shadows
  Ratio:      High contrast, chiaroscuro-inspired

ATMOSPHERE
  Overall:    Exclusive, crafted, timeless
  Texture:    Premium material study
  Feel:       Confident restraint, unhurried elegance

CAMERA ENERGY
  Baseline:   Slow, deliberate
  Progression: Maintain restraint throughout
```

### Shot List

| # | Beat | Duration | Camera | Subject | Key Moment |
|---|------|----------|--------|---------|------------|
| 1 | Establishing | 8s | Slow crane up | Atelier environment | The world of craft |
| 2 | Journey | 6s | Slow tracking | Tools, materials | The making |
| 3 | Discovery | 6s | Push in | Watch emerging | The creation |
| 4 | Connection | 6s | Static + light | Hands on watch | Human touch |
| 5 | Resolution | 8s | Slow pull out | Watch on display | Timeless arrival |

### Full Prompts

**Shot 1 - Establishing (8s)**
```
Slow crane up revealing luxury watchmaker atelier,
warm light cutting through darkness onto workbench,
deep rich black environment with warm gold light accents,
hard directional lighting creating dramatic shadows,
exclusive atmosphere, the world of master craftsmen,
heritage and precision
```

**Shot 2 - Journey (6s)**
```
Slow tracking past precision tools and components,
polished metal catching hard directional light,
deep blacks with warm gold specular highlights,
hard key light sculpting forms in shadow,
exclusive premium atmosphere, the tools of creation,
deliberate craftsmanship journey
```

**Shot 3 - Discovery (6s)**
```
Slow push in as watch emerges from shadow into light,
dial and hands catching directional illumination,
deep rich blacks with warm gold and cream accents,
hard single source creating dramatic reveal,
exclusive atmosphere, the timepiece revealed,
moment of recognition
```

**Shot 4 - Connection (6s)**
```
Static camera, hands gently handling completed watch,
warm light on skin, cold light on metal contrast,
deep blacks with warm gold highlights on surfaces,
hard directional light with intimate feeling,
exclusive atmosphere, human touch meets precision,
connection to craft
```

**Shot 5 - Resolution (8s)**
```
Slow pull out from watch displayed on dark surface,
single beam traveling across, dust motes visible,
deep rich black with warm gold ambient glow,
hard directional key with soft fill emerging,
exclusive premium atmosphere elevated,
timeless, arrived, heritage achieved
```

### Validation Notes

**Single-Prompt Validation**: All PASSED

**Cross-Shot Continuity**: PASSED
- Color palette: "deep rich blacks with warm gold" - consistent
- Lighting: "hard directional" - consistent
- Atmosphere: "exclusive atmosphere" - consistent
- Camera energy: slow throughout (appropriate for luxury)

### Generation Command

```bash
npx ts-node scripts/veo-multi-generate.ts \
  --shots "[Shot 1 prompt]:::[Shot 2 prompt]:::[Shot 3 prompt]:::[Shot 4 prompt]:::[Shot 5 prompt]" \
  --durations "8,6,6,6,8" \
  --output ./output \
  --project-name heritage-watch \
  --resolution 1080p \
  --assemble \
  --transition crossfade \
  --transition-duration 0.75
```

### Assembly Settings

- **Transition**: Crossfade (0.75s - longer for luxury feel)
- **Total Duration**: ~31s
- **Post-production**: Orchestral score, brand end card

---

## Example 3: Fitness App Social Ad

**Use Case**: Instagram Reels / TikTok ad for fitness tracking app
**Template**: Social Ad (3 shots)
**Visual DNA**: Custom (energetic tech)
**Total Duration**: ~18 seconds
**Estimated Cost**: ~$1.50
**Aspect Ratio**: 9:16 (vertical)

### Visual DNA Definition

```
VISUAL DNA: FitPulse App Social Ad
==================================

COLOR PALETTE
  Primary:    Electric teal (#06b6d4)
  Secondary:  Coral energy (#f97316)
  Accent:     Pure white for data
  Contrast:   High, punchy

LIGHTING STYLE
  Quality:    Dynamic, energetic
  Direction:  Multiple sources, neon-inspired
  Mood:       High energy, vibrant

ATMOSPHERE
  Overall:    Kinetic, motivating, aspirational
  Texture:    Data streams, energy particles
  Feel:       Movement, achievement, momentum

CAMERA ENERGY
  Baseline:   Dynamic, energetic
  Progression: High energy maintained throughout
```

### Shot List

| # | Beat | Duration | Camera | Subject | Key Moment |
|---|------|----------|--------|---------|------------|
| 1 | Hook | 6s | Fast push in | Energy burst | Immediate attention |
| 2 | Message | 6s | Dynamic tracking | App metrics | Value clear |
| 3 | CTA Setup | 6s | Converging | Interface glow | Ready for action |

### Full Prompts

**Shot 1 - Hook (6s)**
```
Fast push in through burst of kinetic energy particles,
electric teal and coral streams exploding outward from frame one,
high contrast dynamic lighting, multiple color sources,
kinetic energetic atmosphere, immediate visual impact,
attention-grabbing motion from first frame
```

**Shot 2 - Message (6s)**
```
Dynamic tracking following abstract fitness metrics flowing,
heart rate, steps, achievement icons in energetic motion,
electric teal with coral accent highlights, high contrast,
dynamic lighting with neon-inspired glow,
kinetic atmosphere, value proposition clear, momentum building
```

**Shot 3 - CTA Setup (6s)**
```
Converging motion toward centered abstract app interface,
metrics flowing inward, energy collecting at center point,
electric teal and coral with white data accents,
dynamic lighting focusing toward center,
kinetic atmosphere resolving, ready for action,
clean space for text overlay
```

### Validation Notes

**Single-Prompt Validation**: All PASSED

**Cross-Shot Continuity**: PASSED
- Color palette: "electric teal and coral" - consistent
- Lighting: "dynamic lighting" - consistent
- Atmosphere: "kinetic atmosphere" - consistent
- Camera energy: dynamic throughout (appropriate for social)

### Generation Command

```bash
npx ts-node scripts/veo-multi-generate.ts \
  --shots "[Shot 1 prompt]:::[Shot 2 prompt]:::[Shot 3 prompt]" \
  --durations "6,6,6" \
  --output ./output \
  --project-name fitpulse-ad \
  --aspect-ratio 9:16 \
  --assemble \
  --transition cut
```

### Assembly Settings

- **Transition**: Cut (maintains energy)
- **Total Duration**: 18s
- **Post-production**: Add music, text overlays, CTA button

---

## Example 4: B2B Explainer Video

**Use Case**: Explaining complex workflow automation for enterprise
**Template**: Explainer (4 shots)
**Visual DNA**: Corporate
**Total Duration**: ~26 seconds
**Estimated Cost**: ~$2.00

### Visual DNA Definition

```
VISUAL DNA: WorkflowPro Enterprise Explainer
============================================

COLOR PALETTE
  Primary:    Professional navy (#1e3a5f)
  Secondary:  Warm gray (#6b7280)
  Accent:     Growth green (#059669)
  Treatment:  Medium contrast, accessible

LIGHTING STYLE
  Quality:    Soft, diffused, professional
  Direction:  Even illumination
  Mood:       Trustworthy, clear, competent

ATMOSPHERE
  Overall:    Capable, organized, forward-moving
  Texture:    Clean data visualization
  Feel:       Confident competence

CAMERA ENERGY
  Baseline:   Moderate, purposeful
  Progression: Steady build toward resolution
```

### Shot List

| # | Beat | Duration | Camera | Subject | Key Moment |
|---|------|----------|--------|---------|------------|
| 1 | Problem | 6s | Static | Chaotic workflow | The challenge |
| 2 | Insight | 6s | Push in | Clarity emerges | The aha |
| 3 | Solution | 8s | Tracking | System working | It works |
| 4 | Outcome | 6s | Pull out | Scaled success | Results |

### Full Prompts

**Shot 1 - Problem (6s)**
```
Static camera observing scattered abstract workflow elements,
multiple disconnected pathways crossing chaotically,
professional navy palette with muted tones,
soft diffused lighting, even but without energy,
professional atmosphere with friction,
disorganized complexity, the challenge visible
```

**Shot 2 - Insight (6s)**
```
Smooth push in as organizing connection illuminates,
single clear pathway emerging from complexity,
professional navy with green accent appearing,
soft diffused lighting brightening,
professional atmosphere clearing,
moment of understanding, the insight emerges
```

**Shot 3 - Solution (8s)**
```
Steady tracking following organized workflow in motion,
clean pathways with purpose, data flowing smoothly,
professional navy with green success accents,
soft diffused professional lighting,
professional atmosphere confident,
solution working, competence demonstrated
```

**Shot 4 - Outcome (6s)**
```
Smooth pull out revealing expanded workflow ecosystem,
multiple organized streams operating harmoniously,
professional navy with warm green highlights,
soft diffused lighting elevated and optimistic,
professional atmosphere of achievement,
scaled success, results visible
```

### Validation Notes

**Single-Prompt Validation**: All PASSED

**Cross-Shot Continuity**: PASSED
- Color palette: "professional navy" - consistent
- Lighting: "soft diffused lighting" - consistent
- Atmosphere: "professional atmosphere" - consistent
- Camera energy: steady progression (static → push → tracking → pull)

### Generation Command

```bash
npx ts-node scripts/veo-multi-generate.ts \
  --shots "[Shot 1 prompt]:::[Shot 2 prompt]:::[Shot 3 prompt]:::[Shot 4 prompt]" \
  --durations "6,6,8,6" \
  --output ./output \
  --project-name workflowpro-explainer \
  --assemble \
  --transition crossfade
```

### Assembly Settings

- **Transition**: Crossfade (0.5s)
- **Total Duration**: ~24.5s
- **Post-production**: Voiceover narration, music, text labels

---

## Quick Reference: Prompt Patterns

### Visual DNA Phrases to Reuse

**Tech/SaaS**:
```
cool blue palette with warm amber accents
soft diffused lighting with subtle rim separation
ethereal tech atmosphere
```

**Luxury/Premium**:
```
deep rich blacks with warm gold accents
hard directional lighting with dramatic shadows
exclusive premium atmosphere
```

**Corporate**:
```
professional navy palette with [green/teal] highlights
soft diffused professional lighting
professional atmosphere
```

**Energetic/Social**:
```
[primary] with [secondary] accent highlights
dynamic lighting with high contrast
kinetic energetic atmosphere
```

### Camera Progression Patterns

**Building Drama**: Static → Push → Orbit → Pull
**Steady Journey**: Dolly → Dolly → Dolly → Pull
**Energy Burst**: Fast Push → Tracking → Converging
**Contemplative**: Static → Static → Slow Push → Crane

### Transition Recommendations

| Content Type | Transition | Duration |
|--------------|------------|----------|
| Tech/SaaS | Crossfade | 0.5s |
| Luxury | Crossfade | 0.75s |
| Social/Energy | Cut | - |
| Corporate | Crossfade | 0.5s |
| Dramatic | Fade-black | 0.5s |
