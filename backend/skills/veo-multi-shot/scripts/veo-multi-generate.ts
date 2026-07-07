#!/usr/bin/env npx ts-node
/**
 * Veo Multi-Shot Video Generation Script
 *
 * Batch generation orchestrator for multi-clip video projects.
 * Generates multiple clips sequentially with progress reporting,
 * validates Visual DNA consistency, and optionally triggers assembly.
 *
 * Usage:
 *   npx ts-node veo-multi-generate.ts \
 *     --shots "prompt1:::prompt2:::prompt3" \
 *     --durations "8,6,6" \
 *     --output ./output/ \
 *     --project-name "product-launch"
 *
 * Environment:
 *   GOOGLE_CLOUD_PROJECT - GCP project ID
 *   GOOGLE_CLOUD_LOCATION - Region (default: us-central1)
 *   GOOGLE_APPLICATION_CREDENTIALS - Path to service account JSON
 */

import * as fs from 'fs'
import * as path from 'path'
import { execFileSync, spawnSync } from 'child_process'

// Import the generation function from the single-shot veo skill
// Use relative path from this script's location
const veoGeneratePath = path.resolve(__dirname, '../../veo/scripts/veo-generate.ts')

// ============================================================================
// Types
// ============================================================================

interface MultiShotConfig {
  shots: string[]
  durations: (4 | 6 | 8)[]
  outputDir: string
  projectName: string
  aspectRatio?: '16:9' | '9:16'
  resolution?: '720p' | '1080p'
  generateAudio?: boolean
  assemble?: boolean
  transition?: 'cut' | 'crossfade' | 'fade-black'
  transitionDuration?: number
}

interface ShotResult {
  shotNumber: number
  beatName: string
  prompt: string
  duration: number
  success: boolean
  videoPath?: string
  error?: string
  processingTimeMs?: number
}

interface MultiShotResult {
  success: boolean
  projectName: string
  totalShots: number
  successfulShots: number
  failedShots: number
  results: ShotResult[]
  outputDir: string
  assembledPath?: string
  totalProcessingTimeMs: number
  estimatedCost: string
}

// ============================================================================
// Visual DNA Validation
// ============================================================================

interface VisualDNACheck {
  colorPalette: string[]
  lighting: string[]
  atmosphere: string[]
  cameraEnergy: string[]
}

function extractVisualDNAKeywords(prompt: string): {
  colors: string[]
  lighting: string[]
  atmosphere: string[]
  energy: string[]
} {
  const prompt_lower = prompt.toLowerCase()

  // Common color keywords
  const colorKeywords = [
    'blue', 'cool blue', 'warm amber', 'gold', 'teal', 'cyan',
    'neutral', 'earth tone', 'monochromatic', 'desaturated',
    'rich black', 'deep black', 'lifted black', 'crushed shadow'
  ]

  // Lighting keywords
  const lightingKeywords = [
    'soft diffused', 'hard directional', 'dramatic', 'high contrast',
    'low contrast', 'rim light', 'backlit', 'side-lit', 'ambient',
    'specular', 'even illumination'
  ]

  // Atmosphere keywords
  const atmosphereKeywords = [
    'ethereal', 'premium', 'professional', 'exclusive', 'industrial',
    'organic', 'contemplative', 'kinetic', 'serene', 'dramatic'
  ]

  // Camera energy keywords
  const energyKeywords = [
    'slow', 'measured', 'deliberate', 'moderate', 'dynamic', 'fast',
    'smooth', 'controlled', 'gentle', 'subtle'
  ]

  return {
    colors: colorKeywords.filter(k => prompt_lower.includes(k)),
    lighting: lightingKeywords.filter(k => prompt_lower.includes(k)),
    atmosphere: atmosphereKeywords.filter(k => prompt_lower.includes(k)),
    energy: energyKeywords.filter(k => prompt_lower.includes(k))
  }
}

function validateVisualDNAConsistency(prompts: string[]): {
  valid: boolean
  warnings: string[]
  analysis: VisualDNACheck
} {
  const warnings: string[] = []
  const analysis: VisualDNACheck = {
    colorPalette: [],
    lighting: [],
    atmosphere: [],
    cameraEnergy: []
  }

  // Extract keywords from all prompts
  const allExtractions = prompts.map((p, i) => ({
    shot: i + 1,
    ...extractVisualDNAKeywords(p)
  }))

  // Check for consistency
  const firstShot = allExtractions[0]

  for (let i = 1; i < allExtractions.length; i++) {
    const shot = allExtractions[i]

    // Check if lighting style is dramatically different
    const firstHasHard = firstShot.lighting.some(l => l.includes('hard'))
    const shotHasHard = shot.lighting.some(l => l.includes('hard'))
    const firstHasSoft = firstShot.lighting.some(l => l.includes('soft'))
    const shotHasSoft = shot.lighting.some(l => l.includes('soft'))

    if ((firstHasHard && shotHasSoft) || (firstHasSoft && shotHasHard)) {
      warnings.push(
        `WARNING: Lighting style mismatch between Shot 1 and Shot ${i + 1}. ` +
        `Shot 1: ${firstShot.lighting.join(', ') || 'none detected'}. ` +
        `Shot ${i + 1}: ${shot.lighting.join(', ') || 'none detected'}.`
      )
    }

    // Check for atmosphere consistency
    if (firstShot.atmosphere.length > 0 && shot.atmosphere.length > 0) {
      const overlap = firstShot.atmosphere.filter(a => shot.atmosphere.includes(a))
      if (overlap.length === 0) {
        warnings.push(
          `WARNING: Atmosphere mismatch between Shot 1 and Shot ${i + 1}. ` +
          `Shot 1: ${firstShot.atmosphere.join(', ')}. ` +
          `Shot ${i + 1}: ${shot.atmosphere.join(', ')}.`
        )
      }
    }
  }

  // Store analysis
  analysis.colorPalette = [...new Set(allExtractions.flatMap(e => e.colors))]
  analysis.lighting = [...new Set(allExtractions.flatMap(e => e.lighting))]
  analysis.atmosphere = [...new Set(allExtractions.flatMap(e => e.atmosphere))]
  analysis.cameraEnergy = [...new Set(allExtractions.flatMap(e => e.energy))]

  return {
    valid: warnings.length === 0,
    warnings,
    analysis
  }
}

// ============================================================================
// Generation
// ============================================================================

async function generateSingleShot(
  prompt: string,
  duration: 4 | 6 | 8,
  outputPath: string,
  aspectRatio: '16:9' | '9:16',
  resolution: '720p' | '1080p',
  generateAudio: boolean
): Promise<{ success: boolean; videoPath?: string; error?: string; processingTimeMs?: number }> {
  const startTime = Date.now()

  try {
    // Build arguments array for execFile (safer than exec - prevents shell injection)
    const args = [
      'ts-node', veoGeneratePath,
      '--prompt', prompt,
      '--aspect-ratio', aspectRatio,
      '--duration', duration.toString(),
      '--resolution', resolution,
      '--output', outputPath
    ]

    if (generateAudio) {
      args.push('--audio')
    }

    // Use spawnSync for safer execution (no shell)
    const result = spawnSync('npx', args, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 600000, // 10 minute timeout
    })

    if (result.error) {
      return {
        success: false,
        error: result.error.message,
        processingTimeMs: Date.now() - startTime
      }
    }

    // Check if file exists
    if (fs.existsSync(outputPath)) {
      return {
        success: true,
        videoPath: outputPath,
        processingTimeMs: Date.now() - startTime
      }
    } else {
      return {
        success: false,
        error: result.stderr || 'Video file not created',
        processingTimeMs: Date.now() - startTime
      }
    }
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      processingTimeMs: Date.now() - startTime
    }
  }
}

async function generateMultiShot(config: MultiShotConfig): Promise<MultiShotResult> {
  const startTime = Date.now()
  const results: ShotResult[] = []

  console.log('\n' + '='.repeat(60))
  console.log('VEO MULTI-SHOT GENERATION')
  console.log('='.repeat(60))
  console.log(`Project: ${config.projectName}`)
  console.log(`Shots: ${config.shots.length}`)
  console.log(`Total estimated duration: ~${config.durations.reduce((a, b) => a + b, 0)}s`)
  console.log(`Estimated cost: ~$${(config.shots.length * 0.5).toFixed(2)}`)
  console.log('='.repeat(60) + '\n')

  // Validate Visual DNA consistency
  console.log('Validating Visual DNA consistency...')
  const dnaValidation = validateVisualDNAConsistency(config.shots)

  if (!dnaValidation.valid) {
    console.log('\n  VISUAL DNA WARNINGS:')
    dnaValidation.warnings.forEach(w => console.log(`   ${w}`))
    console.log('\nProceeding with generation despite warnings.\n')
  } else {
    console.log('  Visual DNA consistency validated\n')
  }

  console.log('Visual DNA Analysis:')
  console.log(`   Colors: ${dnaValidation.analysis.colorPalette.join(', ') || 'none detected'}`)
  console.log(`   Lighting: ${dnaValidation.analysis.lighting.join(', ') || 'none detected'}`)
  console.log(`   Atmosphere: ${dnaValidation.analysis.atmosphere.join(', ') || 'none detected'}`)
  console.log(`   Energy: ${dnaValidation.analysis.cameraEnergy.join(', ') || 'none detected'}`)
  console.log('')

  // Create output directory
  const projectDir = path.join(config.outputDir, config.projectName)
  if (!fs.existsSync(projectDir)) {
    fs.mkdirSync(projectDir, { recursive: true })
  }

  // Generate beat names based on number of shots
  const beatNames = getBeatNames(config.shots.length)

  // Generate each shot
  for (let i = 0; i < config.shots.length; i++) {
    const shotNum = i + 1
    const prompt = config.shots[i]
    const duration = config.durations[i] || 6
    const beatName = beatNames[i]
    const paddedNum = shotNum.toString().padStart(2, '0')
    const outputPath = path.join(projectDir, `shot-${paddedNum}-${beatName.toLowerCase().replace(/\s+/g, '-')}.mp4`)

    console.log(`[${shotNum}/${config.shots.length}] ${beatName} (${duration}s)`)
    console.log(`   Prompt: "${prompt.substring(0, 60)}${prompt.length > 60 ? '...' : ''}"`)

    const result = await generateSingleShot(
      prompt,
      duration as 4 | 6 | 8,
      outputPath,
      config.aspectRatio || '16:9',
      config.resolution || '720p',
      config.generateAudio || false
    )

    if (result.success) {
      console.log(`     Complete (${((result.processingTimeMs || 0) / 1000).toFixed(1)}s)`)
      console.log(`   -> ${outputPath}\n`)
    } else {
      console.log(`     Failed: ${result.error}\n`)
    }

    results.push({
      shotNumber: shotNum,
      beatName,
      prompt,
      duration,
      success: result.success,
      videoPath: result.videoPath,
      error: result.error,
      processingTimeMs: result.processingTimeMs
    })
  }

  // Summary
  const successCount = results.filter(r => r.success).length
  const failCount = results.filter(r => !r.success).length

  console.log('='.repeat(60))
  console.log('GENERATION COMPLETE')
  console.log('='.repeat(60))
  console.log(`Successful: ${successCount}/${config.shots.length}`)
  console.log(`Failed: ${failCount}/${config.shots.length}`)
  console.log(`Output: ${projectDir}`)

  // Assembly if requested and all shots succeeded
  let assembledPath: string | undefined
  if (config.assemble && successCount === config.shots.length) {
    console.log('\nAssembling clips...')
    assembledPath = await assembleClips(
      results.filter(r => r.success).map(r => r.videoPath!),
      path.join(projectDir, `${config.projectName}-assembled.mp4`),
      config.transition || 'crossfade',
      config.transitionDuration || 0.5
    )
    if (assembledPath) {
      console.log(`  Assembled: ${assembledPath}`)
    }
  } else if (config.assemble && failCount > 0) {
    console.log('\nSkipping assembly due to failed shots.')
  }

  console.log('='.repeat(60) + '\n')

  return {
    success: failCount === 0,
    projectName: config.projectName,
    totalShots: config.shots.length,
    successfulShots: successCount,
    failedShots: failCount,
    results,
    outputDir: projectDir,
    assembledPath,
    totalProcessingTimeMs: Date.now() - startTime,
    estimatedCost: `$${(config.shots.length * 0.5).toFixed(2)}`
  }
}

function getBeatNames(shotCount: number): string[] {
  switch (shotCount) {
    case 3:
      return ['Hook', 'Message', 'CTA']
    case 4:
      return ['Teaser', 'Reveal', 'Detail', 'Context']
    case 5:
      return ['Establishing', 'Journey', 'Discovery', 'Connection', 'Resolution']
    default:
      return Array.from({ length: shotCount }, (_, i) => `Shot ${i + 1}`)
  }
}

// ============================================================================
// Assembly
// ============================================================================

async function assembleClips(
  clipPaths: string[],
  outputPath: string,
  transition: 'cut' | 'crossfade' | 'fade-black',
  transitionDuration: number
): Promise<string | undefined> {
  try {
    const assemblyScript = path.resolve(__dirname, 'assemble-clips.sh')

    if (!fs.existsSync(assemblyScript)) {
      console.log('   Assembly script not found, skipping assembly.')
      return undefined
    }

    // Use execFileSync for safer execution (no shell injection)
    const result = spawnSync(assemblyScript, [
      '--clips', clipPaths.join(','),
      '--transition', transition,
      '--transition-duration', transitionDuration.toString(),
      '--output', outputPath
    ], {
      encoding: 'utf-8',
      stdio: 'inherit'
    })

    if (result.error) {
      console.log(`   Assembly failed: ${result.error.message}`)
      return undefined
    }

    if (fs.existsSync(outputPath)) {
      return outputPath
    }

    return undefined
  } catch (error) {
    console.log(`   Assembly failed: ${error instanceof Error ? error.message : String(error)}`)
    return undefined
  }
}

// ============================================================================
// CLI
// ============================================================================

function printUsage(): void {
  console.log(`
Veo Multi-Shot Video Generation

Usage:
  npx ts-node veo-multi-generate.ts --shots "p1:::p2:::p3" --durations "8,6,6" [options]

Required:
  --shots             Prompts separated by ::: delimiter
  --durations         Comma-separated durations (4, 6, or 8)
  --output            Output directory path
  --project-name      Project name (creates subdirectory)

Options:
  --aspect-ratio      16:9 or 9:16 (default: 16:9)
  --resolution        720p or 1080p (default: 720p)
  --audio             Enable audio generation (default: false)
  --assemble          Assemble clips after generation
  --transition        cut, crossfade, or fade-black (default: crossfade)
  --transition-duration  Transition length in seconds (default: 0.5)
  --help, -h          Show this help message

Environment Variables:
  GOOGLE_CLOUD_PROJECT              GCP project ID (required)
  GOOGLE_CLOUD_LOCATION             Region (default: us-central1)
  GOOGLE_APPLICATION_CREDENTIALS    Path to service account JSON (required)

Examples:
  # Product launch (4 shots)
  npx ts-node veo-multi-generate.ts \\
    --shots "teaser prompt:::reveal prompt:::detail prompt:::context prompt" \\
    --durations "8,6,6,6" \\
    --output ./output \\
    --project-name product-launch \\
    --assemble

  # Social ad (3 shots, vertical)
  npx ts-node veo-multi-generate.ts \\
    --shots "hook:::message:::cta" \\
    --durations "6,6,6" \\
    --output ./output \\
    --project-name social-ad \\
    --aspect-ratio 9:16 \\
    --assemble \\
    --transition cut
`)
}

function parseArgs(args: string[]): MultiShotConfig | null {
  const config: Partial<MultiShotConfig> = {
    aspectRatio: '16:9',
    resolution: '720p',
    generateAudio: false,
    assemble: false,
    transition: 'crossfade',
    transitionDuration: 0.5
  }

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    const next = args[i + 1]

    switch (arg) {
      case '--help':
      case '-h':
        printUsage()
        return null

      case '--shots':
        config.shots = next?.split(':::').map(s => s.trim()) || []
        i++
        break

      case '--durations':
        config.durations = next?.split(',').map(d => {
          const num = parseInt(d.trim(), 10)
          if (num === 4 || num === 6 || num === 8) return num
          return 6 // default
        }) as (4 | 6 | 8)[]
        i++
        break

      case '--output':
        config.outputDir = next
        i++
        break

      case '--project-name':
        config.projectName = next
        i++
        break

      case '--aspect-ratio':
        if (next === '16:9' || next === '9:16') {
          config.aspectRatio = next
        }
        i++
        break

      case '--resolution':
        if (next === '720p' || next === '1080p') {
          config.resolution = next
        }
        i++
        break

      case '--audio':
        config.generateAudio = true
        break

      case '--assemble':
        config.assemble = true
        break

      case '--transition':
        if (next === 'cut' || next === 'crossfade' || next === 'fade-black') {
          config.transition = next
        }
        i++
        break

      case '--transition-duration':
        config.transitionDuration = parseFloat(next) || 0.5
        i++
        break
    }
  }

  // Validation
  if (!config.shots || config.shots.length === 0) {
    console.error('Error: --shots is required\n')
    printUsage()
    return null
  }

  if (!config.durations || config.durations.length === 0) {
    console.error('Error: --durations is required\n')
    printUsage()
    return null
  }

  if (!config.outputDir) {
    console.error('Error: --output is required\n')
    printUsage()
    return null
  }

  if (!config.projectName) {
    console.error('Error: --project-name is required\n')
    printUsage()
    return null
  }

  // Pad durations if needed
  while (config.durations.length < config.shots.length) {
    config.durations.push(6)
  }

  return config as MultiShotConfig
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)

  if (args.length === 0) {
    printUsage()
    process.exit(0)
  }

  const config = parseArgs(args)
  if (!config) {
    process.exit(1)
  }

  const result = await generateMultiShot(config)

  if (result.success) {
    console.log('Multi-shot generation completed successfully.')
    process.exit(0)
  } else {
    console.error('Some shots failed to generate.')
    process.exit(1)
  }
}

// Export for programmatic use
export { generateMultiShot, MultiShotConfig, MultiShotResult, validateVisualDNAConsistency }

// Run if executed directly
main().catch((err) => {
  console.error('Fatal error:', err)
  process.exit(1)
})
