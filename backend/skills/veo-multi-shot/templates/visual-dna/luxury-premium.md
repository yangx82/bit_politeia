# Visual DNA: Luxury / Premium

A visual language preset for high-end products, luxury brands, and premium positioning.

---

## Overview

| Attribute | Value |
|-----------|-------|
| Industries | Luxury goods, premium brands, high-end services, automotive, jewelry, fashion |
| Feeling | Exclusive, crafted, aspirational, refined |
| Energy | Measured, confident, unhurried |

---

## Locked Parameters

### Color Palette

```
PRIMARY:    Deep neutrals (rich blacks, dark charcoals)
            #0a0a0a to #1a1a1a
            Foundation of sophistication

SECONDARY:  Warm metallics (gold, bronze, copper tones)
            #b8860b, #cd7f32, #d4a574
            Luxury material reference

ACCENT:     Cream / Warm white
            #f5f5dc, #faf8f5
            Contrast and highlight

SHADOWS:    Rich, deep, not muddy
            Crushed blacks with detail

HIGHLIGHTS: Warm, glowing, specular on materials
            Premium surface quality
```

**Prompt Keywords**: `deep rich blacks`, `warm gold accents`, `cream highlights`, `crushed shadows with detail`

### Lighting Style

```
QUALITY:    Hard, directional, sculpted
            Creates drama and dimension

DIRECTION:  Strong key with minimal fill
            Chiaroscuro-inspired

RATIO:      High contrast, dramatic
            Shadows are features, not problems

SPECULAR:   Prominent on premium materials
            Shows surface quality

ATMOSPHERE: Minimal haze, clean air
            Nothing obscuring the craft
```

**Prompt Keywords**: `hard directional lighting`, `high contrast`, `dramatic shadows`, `specular highlights on surfaces`

### Atmosphere / Mood

```
OVERALL:    Exclusive, crafted, aspirational
            Unattainable but desirable

TEXTURE:    Material-focused, tactile quality
            You can feel the surface

SPACE:      Generous negative space, breathing room
            Never cluttered or busy

FEEL:       Confident restraint, quiet power
            Doesn't need to shout
```

**Prompt Keywords**: `exclusive atmosphere`, `premium tactile quality`, `generous negative space`, `confident restraint`

### Camera Energy

```
BASELINE:   Slow, deliberate, unhurried
            Time is a luxury

MOVEMENTS:  Precise, controlled, intentional
            Every frame composed

SPEED:      Slower than comfortable
            Demands attention

PROGRESSION: Maintain restraint throughout
             Consistency is the luxury
```

**Prompt Keywords**: `slow deliberate movement`, `unhurried pacing`, `precise camera`, `controlled motion`

---

## Variable Parameters (Per Shot)

### Camera Movement Options

| Movement | Best For | Energy |
|----------|----------|--------|
| Slow orbit | Product examination, jewelry | Low |
| Slow push in | Detail reveal, focus | Low |
| Static with moving light | Material study, texture | Lowest |
| Slow crane | Environment, scale | Low |
| Pull out | Context, aspiration | Low-Med |

### Shot Size Options

| Size | Best For |
|------|----------|
| Wide | Environment, lifestyle context |
| Medium | Product in setting, hero shot |
| Close-up | Material detail, craftsmanship |
| Macro | Texture, finish, precision |

---

## Prompt Templates

### Material Study Shot
```
[Static / slow orbit], [extreme close-up / macro] of [specific luxury material],
[single hard light source] creating [traveling highlight / deep shadow],
deep rich blacks with warm gold accents, high contrast dramatic lighting,
premium surface detail visible, exclusive atmosphere, [material adjective] craftsmanship
```

### Product Hero Shot
```
[Slow camera movement] [toward/around] [product description],
[light sculpting form], [material finish description],
deep blacks with warm metallic accents, hard directional lighting,
generous negative space, exclusive premium atmosphere, [aspiration word]
```

### Environment / Context Shot
```
[Slow camera movement] through [luxury environment descriptor],
[premium materials and surfaces], [light quality description],
rich neutral palette with warm accent highlights, dramatic lighting,
exclusive atmosphere, unhurried elegance, [lifestyle aspiration]
```

### Detail / Craftsmanship Shot
```
[Macro / intimate] view of [specific craft detail],
[light revealing precision / texture / finish],
deep shadows with warm highlight accents, hard directional key,
exclusive atmosphere, visible craftsmanship, [quality descriptor]
```

---

## Example Prompts

### Luxury Watch Product Launch

**Shot 1 (Teaser)**:
```
Slow dolly forward through minimal dark space,
single beam of warm light suggesting form ahead,
deep rich black environment with warm gold light accent,
hard directional beam cutting through darkness,
exclusive atmosphere, anticipation building, something precious awaits
```

**Shot 2 (Reveal)**:
```
Slow push in as watch emerges from shadow into light,
polished steel catching hard directional light, dial gradually illuminating,
deep blacks with warm gold and cream accents, dramatic single key light,
exclusive premium atmosphere, first reveal, refined beauty
```

**Shot 3 (Detail)**:
```
Slow orbit, macro lens, brushed steel case surface,
hard light traveling across revealing microscopic finishing,
deep shadows with warm specular highlights, dramatic contrast,
exclusive atmosphere, visible craftsmanship, precision engineering
```

**Shot 4 (Context)**:
```
Slow pull out revealing watch on dark leather surface,
warm ambient light from side, negative space surrounding,
deep rich blacks with warm gold ambient, hard key with soft fill,
exclusive atmosphere, unhurried elegance, aspiration realized
```

---

## Material-Specific Guidance

### Metallic Surfaces (Gold, Steel, Chrome)
- Emphasize specular highlights
- Hard lighting shows polish
- Add: `specular highlights traveling across surface`

### Leather / Fabric
- Side lighting reveals texture
- Softer shadows than hard surfaces
- Add: `light revealing texture and grain`

### Glass / Crystal
- Backlight or side-light for caustics
- Emphasize refraction
- Add: `light refracting through`, `prismatic`

### Wood / Natural Materials
- Warm lighting enhances warmth
- Show grain and figure
- Add: `grain visible`, `natural warmth`

---

## Variations

### Contemporary Luxury (Fashion, Design)
- More contrast, bolder compositions
- Can include color accents
- Add: `bold`, `contemporary`, `statement`

### Heritage Luxury (Watches, Traditional)
- Warmer overall, more gold tones
- Emphasis on craft and detail
- Add: `heritage`, `timeless`, `generations`

### Minimalist Luxury (Scandinavian, Modern)
- More neutral, less warm
- Even more negative space
- Add: `minimal`, `essential`, `pure`

---

## Continuity Checklist

When using this Visual DNA across multiple shots, verify:

- [ ] "deep rich blacks" or "dark neutral" appears in ALL prompts
- [ ] "hard directional lighting" or "dramatic lighting" in ALL prompts
- [ ] "exclusive atmosphere" or "premium atmosphere" in ALL prompts
- [ ] Warm accent (gold/bronze/cream) consistent across prompts
- [ ] Camera energy is consistently slow/measured
- [ ] No prompt uses soft/diffused lighting (breaks luxury look)
- [ ] No prompt feels rushed or energetic
