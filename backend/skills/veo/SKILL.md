---
name: veo
description: AI video generation using Google Veo 3 via Vertex AI. Creates short-form video content optimized for landing pages, marketing materials, and UI backgrounds. Supports text-to-video generation with automatic prompt engineering for seamless loops, hero sections, and ambient motion.
---

This skill transforms user intent into cinematic video using Google Veo 3.1. Every frame deliberate. Every movement purposeful. Generate videos that burn into memory—not generic stock footage that fades into noise.

---

## Workflow (FOLLOW IN ORDER)

**CRITICAL**: Follow these phases sequentially. Never skip validation. Never generate without user approval.

### PHASE 1: UNDERSTAND

Before crafting any prompt, gather context through conversation:

**Required Context:**
- **USE CASE**: hero-background | marketing | social | product | ambient
- **MOOD**: ethereal | kinetic | contemplative | industrial | organic | futuristic | vintage | dramatic | abstract
- **TECHNICAL REQUIREMENTS**: aspect ratio, duration, resolution needs
- **ANTI-GOALS**: What must NOT appear (competing brands, specific imagery to avoid)

**If the user request is vague, ASK clarifying questions:**

```
Before I craft your prompt, I need to understand:
1. Where will this video be used? (hero background, social media, product page)
2. What mood or feeling should it evoke?
3. Any brand colors or visual constraints?
4. What should the video absolutely NOT contain?
```

**Vague Request Examples (require clarification):**
- "Make me a video for my website" → Ask: What type of website? What section? What feeling?
- "Create something cool" → Ask: Cool how? Energetic? Mysterious? Futuristic?
- "I need a background video" → Ask: What's the content above it? Tech? Wellness? Finance?

**Clear Request Examples (proceed to Phase 2):**
- "Create a hero background for my SaaS landing page with floating data particles, ethereal blue mood"
- "Generate a product showcase video for a luxury watch, slow orbit, dramatic lighting"

### PHASE 2: CRAFT

Build the prompt using the **5-Element Formula** (see detailed reference below):

```
[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]
```

**Checklist while crafting:**
- [ ] Single camera movement (no stacking)
- [ ] Specific subject with material detail
- [ ] One primary action in present continuous tense
- [ ] Grounded location/temporal context
- [ ] Clear lighting and color direction

For hero backgrounds, ALWAYS include:
- `seamless loop`
- `locked camera` or `static camera`
- Subtle motion descriptors (`gentle`, `slowly`, `imperceptibly`)

Reference `references/cinematography-lexicon.md` for precise terminology.
Reference `examples/hero-prompts.md` for proven patterns.

### PHASE 3: VALIDATE (MANDATORY)

Before presenting to user, verify against `validation/prompt-checklist.md`:

**REJECT (Do Not Generate):**
- [ ] Multiple camera movements ("dolly while panning")
- [ ] Text/UI element requests (Veo cannot render readable text)
- [ ] Conflicting descriptors ("dynamic but subtle", "energetic but calm")

**WARNING (Suggest Improvements):**
- [ ] Generic descriptions without material specificity
- [ ] Missing lighting/atmosphere direction
- [ ] Duration mismatch for content type

**LOOP-SPECIFIC (for hero backgrounds):**
- [ ] Contains "seamless loop"
- [ ] Contains "locked camera" or "static camera"
- [ ] Motion is subtle/gentle (not dramatic)

### PHASE 4: PRESENT & AWAIT APPROVAL

**CRITICAL: Present the prompt and WAIT for explicit user approval before generating.**

Format your presentation as:

```
READY FOR REVIEW:

Prompt:
[Full crafted prompt]

Settings:
- Aspect Ratio: [16:9 | 9:16]
- Duration: [4s | 6s | 8s]
- Resolution: [720p | 1080p]
- Audio: [off | on]

Validation: PASSED
- Single camera movement
- No text requests
- Loop flags present (if applicable)
- Motion intensity appropriate

Shall I generate this video? (Cost: ~$0.50, Time: 2-4 minutes)
```

If validation fails, present issues and suggest fixes:

```
VALIDATION ISSUES FOUND:

Prompt:
[Problematic prompt]

Issues:
- REJECT: Multiple camera movements detected ("dolly while panning")
- WARNING: No material specificity for "metal surface"

Suggested Fix:
[Corrected prompt]

Shall I proceed with the corrected version?
```

### PHASE 5: GENERATE

Only after user approval, execute generation using `scripts/veo-generate.ts`:

```bash
npx ts-node scripts/veo-generate.ts \
  --prompt "your validated prompt" \
  --aspect-ratio 16:9 \
  --duration 6 \
  --resolution 720p \
  --output ./hero-video.mp4
```

Report completion with file path.

### PHASE 6: ITERATE (if unsatisfied)

If the user is not satisfied with results, guide targeted improvements:

**Ask**: "What specifically didn't work?"

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| Too static/boring | Insufficient motion description | Increase motion intensity, add particle effects |
| Too chaotic | Too much action, moving camera | Simplify to single action, lock camera |
| Wrong mood | Style/lighting mismatch | Revisit atmosphere descriptors |
| Doesn't loop well | Motion too complex for loop | Use 4s duration, lock camera, reduce motion |
| Generic output | Lacking material specificity | Add texture/material detail |
| Wrong color feel | Color direction unclear | Add explicit palette direction |

**Iteration Workflow:**
1. Identify specific issue from user feedback
2. Modify relevant prompt element (don't start over)
3. Re-validate the modified prompt
4. Present for approval
5. Generate with same seed for comparison (optional: `--seed [original_seed]`)

---

## Cinematic Thinking

Before generating, understand the context and commit to a BOLD cinematic direction:

- **Purpose**: What story unfolds in 4-8 seconds? Who watches, and where?
- **Mood**: Pick a cinematic register and OWN it:
  - Ethereal/dreamlike — soft focus, floating motion, otherworldly
  - Kinetic/energetic — dynamic cuts, velocity, pulse
  - Contemplative/slow — measured pace, breathing room, stillness
  - Industrial/mechanical — precision, repetition, engineered beauty
  - Organic/natural — growth, flow, imperfection embraced
  - Futuristic/tech — clean geometry, data visualization, tomorrow's aesthetic
  - Vintage/nostalgic — film grain, warm tones, memory texture
  - Dramatic/intense — high contrast, tension, weight
  - Abstract/experimental — break expectations, pure form
- **Camera Philosophy**: One camera. One movement. One moment. Restraint is power.
- **The Unforgettable Frame**: What single frame sears into memory? Design for that.

**CRITICAL**: Veo rewards specificity and professional terminology. Vague prompts produce forgettable videos. Commit to a vision and describe it with the precision of a cinematographer.

---

## The Cinematic Prompt Formula

Construct prompts using five elements. Order matters—lead with camera, end with atmosphere:

**[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]**

### Element 1: Cinematography
Start with ONE camera verb. Never stack movements.

| Movement | Character | Use When |
|----------|-----------|----------|
| `dolly forward/back` | Intimate approach or retreat | Drawing viewer into subject |
| `tracking left/right` | Lateral journey | Revealing space progressively |
| `crane up/down` | Vertical revelation | Showing scale, context |
| `orbit` | 360 degree examination | Product showcase, sculpture |
| `push in` | Intensifying focus | Building tension |
| `pull out` | Expanding context | Revealing environment |
| `static/locked` | Pure observation | Hero backgrounds, loops |
| `handheld` | Organic instability | Documentary feel |
| `rack focus` | Shifting attention | Foreground/background play |

Add lens context when it shapes the image:
- `macro lens` — extreme detail, shallow depth
- `telephoto compression` — flattened planes, intimacy at distance
- `wide establishing` — environmental context, scale

### Element 2: Subject
Be ruthlessly specific. Not "a person" but "a ceramicist in her 70s, clay-dusted apron, silver hair tied back."

Material specificity elevates everything:
- "metal surface" → "brushed titanium with microscopic scratches catching light"
- "water" → "black coffee rippling in a ceramic cup"
- "particles" → "bioluminescent spores drifting upward"

### Element 3: Action
One primary motion. Present continuous tense.

For hero backgrounds, favor subtle over dramatic:
- `particles rising slowly`
- `light shifting imperceptibly`
- `fog rolling across`
- `shadows lengthening`
- `surface rippling gently`

For marketing/product, allow dynamism:
- `rotating to reveal`
- `unfolding in sequence`
- `assembling from fragments`

### Element 4: Context
Ground the subject in space and time.

**Location specificity**:
- "office" → "corner office, floor 47, rain streaking the windows"
- "nature" → "Pacific Northwest forest floor, post-rain, fern-heavy"

**Temporal anchors**:
- `golden hour — last fifteen minutes`
- `blue hour — deep twilight`
- `3AM — sodium street light`
- `overcast noon — flat diffused light`

### Element 5: Style & Ambiance
The emotional finish. Lighting + color + reference.

**Lighting motifs**:
- `single hard source, deep shadows`
- `soft wraparound, minimal contrast`
- `practical lights only, motivated`
- `neon spill, complementary colors`
- `backlit silhouette, rim light separation`

**Color direction**:
- `desaturated earth tones, lifted blacks`
- `high contrast monochrome`
- `split toning — warm highlights, cool shadows`
- `single accent color against neutral`

**Film references** (use sparingly, when apt):
- `Blade Runner 2049 — vast, lonely, amber/teal`
- `Terrence Malick — natural light, magic hour, reverent`
- `Fincher — precise, clinical, desaturated`
- `Wes Anderson — symmetry, pastel, storybook`

---

## Hero Background Mastery

Hero videos serve the text above them. They create atmosphere, not distraction.

### Required Prompt Elements
ALWAYS include for seamless loops:
- `seamless loop` — signals loop intent to model
- `locked camera` or `static camera` — prevents jarring motion
- `subtle motion` or `gentle movement` — visual interest without distraction

### Technical Settings
```
Aspect Ratio: 16:9 (standard hero)
Duration: 4-6 seconds (shorter = smoother loop)
Resolution: 720p (web performance) or 1080p (high-bandwidth)
Audio: disabled (backgrounds are silent)
```

### The Loop Technique
Veo generates linear video. For infinite loops:
1. Generate one clip
2. Duplicate the clip
3. Reverse the duplicate
4. Crossfade at junction points (0.5-1s)
5. Result: mathematically seamless infinite loop

### Design for Darkness
Hero videos get overlaid with text. Plan for 35% darkening:
- High-contrast subjects survive better
- Avoid fine detail that disappears when dimmed
- Light-on-dark scenes work better than dark-on-light
- Test: squint at your mental image—still readable?

### Hero Prompt Templates

**Tech/SaaS — Abstract Data**
```
Slow dolly forward through infinite field of softly glowing data particles, gentle upward drift, deep blue void with purple edge light, seamless loop, locked camera, ethereal tech atmosphere, shallow depth of field
```

**Luxury/Premium — Material Study**
```
Static camera, extreme macro on brushed gold surface, single light source creating traveling highlight, particles of dust suspended in beam, seamless loop, contemplative, Fincher-esque precision
```

**Nature/Wellness — Organic Motion**
```
Locked camera observing morning mist rolling across still lake surface, soft diffused dawn light, mountains barely visible in background, seamless loop, gentle motion, Malick naturalism
```

**Creative/Agency — Bold Abstract**
```
Slow orbit around floating geometric forms, sharp shadows, single saturated accent color against deep black, shapes rotating imperceptibly, seamless loop, modernist, high contrast
```

**Finance/Enterprise — Architectural Stability**
```
Static wide shot of minimalist interior, single beam of light slowly traveling across concrete wall, dust motes visible, seamless loop, locked camera, contemplative corporate, desaturated palette
```

---

## Implementation

### Environment Setup
Required environment variables:
```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Generation Script
Use the included TypeScript script at `scripts/veo-generate.ts`:

```bash
npx ts-node scripts/veo-generate.ts \
  --prompt "your cinematic prompt" \
  --aspect-ratio 16:9 \
  --duration 6 \
  --resolution 720p \
  --output ./hero-video.mp4
```

### API Parameters
| Parameter | Options | Default | Notes |
|-----------|---------|---------|-------|
| `model` | `veo-3.1-generate-001`, `veo-3.1-fast-generate-001` | quality model | Fast model for iteration |
| `aspectRatio` | `16:9`, `9:16` | `16:9` | 9:16 for vertical/mobile |
| `durationSeconds` | `4`, `6`, `8` | `8` | API only supports these values |
| `resolution` | `720p`, `1080p` | `720p` | 1080p for high-bandwidth |
| `generateAudio` | `true`, `false` | `false` | Enable for marketing |
| `sampleCount` | `1-4` | `1` | Multiple variations |
| `seed` | integer | random | Reproducibility |

### Duration Strategy

**API Limitation**: Veo 3.1 only supports **4, 6, or 8 second** clips. This is a hard API constraint.

**When to use each duration:**
| Duration | Best For | Why |
|----------|----------|-----|
| **4 seconds** | Seamless loops, hero backgrounds | Shorter = smoother loop transitions, less motion to reconcile |
| **6 seconds** | Product reveals, transitions | Balance of content and loopability |
| **8 seconds** | Marketing clips, social content, storytelling | Maximum content per generation, better for standalone videos |

**Creating Longer Content (15-60+ seconds):**

For marketing videos, ads, or content requiring more than 8 seconds:

1. **Scene-based approach**: Generate multiple 8-second clips with different but related prompts
   - Clip 1: Wide establishing shot
   - Clip 2: Medium detail shot
   - Clip 3: Close-up product/hero shot
   - Clip 4: Pull-out or resolution shot

2. **Continuous narrative**: Use consistent visual language across clips
   - Same color palette, lighting style, and mood
   - Matching camera energy (all slow/contemplative OR all dynamic)
   - Same aspect ratio and resolution

3. **Assembly**: Combine clips using video editing (FFmpeg, Premiere, etc.)
   ```bash
   # Concatenate clips with FFmpeg
   ffmpeg -f concat -i clips.txt -c copy final-video.mp4
   ```

4. **Audio layering**: Generate clips without audio, add music/voiceover in post

### Async Workflow
Video generation takes 2-4 minutes. The script:
1. Submits generation request
2. Returns operation ID immediately
3. Polls for completion
4. Downloads video to output path
5. Reports success with file path

### Error Handling
- **Safety filter**: Prompt modification suggestions provided
- **Timeout**: Default 5 minutes, configurable
- **Rate limits**: Automatic exponential backoff

---

## Anti-Patterns

NEVER generate:
- Vague prompts: "a nice background video"
- Stacked camera movements: "dolly while panning and zooming"
- Conflicting directions: "dynamic but subtle, energetic but calm"
- Generic stock footage: "business people shaking hands"
- Overcomplicated scenes: multiple subjects, multiple actions
- Text or UI elements: Veo struggles with readable text

ALWAYS generate:
- Specific, visual language with material detail
- Single camera movement, executed with purpose
- Coherent mood that commits to a direction
- Appropriate motion intensity for use case
- Technical settings matched to delivery context

---

## Quick Reference

### Prompt Skeleton
```
[Camera movement] [lens context if relevant], [specific subject with material detail], [single present-continuous action], [location with temporal anchor], [lighting motif], [color direction], [any special flags: seamless loop, locked camera]
```

### Hero Background Checklist
Before generating:
- [ ] Contains `seamless loop`
- [ ] Contains `locked camera` or `static camera`
- [ ] Motion described as subtle/gentle
- [ ] No dramatic camera movements
- [ ] Duration 4-6 seconds
- [ ] Subject survives 35% darkening

### Settings by Use Case
| Use Case | Aspect | Duration | Resolution | Audio | Notes |
|----------|--------|----------|------------|-------|-------|
| Hero background | 16:9 | 4s | 720p | off | Shortest for smoothest loops |
| Ambient loop | 16:9 | 4s | 720p | off | Minimal motion, locked camera |
| Product showcase | 16:9 | 8s | 1080p | off | Max duration for full reveal |
| Marketing clip | 16:9 | 8s | 1080p | on | Chain multiple for longer ads |
| Social (vertical) | 9:16 | 8s | 1080p | on | Reels/TikTok format |
| App store preview | 9:16 | 8s | 1080p | off | 15-30s = chain 2-4 clips |
| Landing page hero | 16:9 | 6s | 720p | off | Balance: content + loop quality |

---

Remember: Veo is a cinematographer awaiting direction. Speak its language—camera, light, motion, material—and it delivers frames worth remembering. Mumble vague requests and receive forgettable footage. The prompt IS the direction. Make it count.
