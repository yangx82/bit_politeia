#!/usr/bin/env npx ts-node
/**
 * Veo Video Generation Script
 *
 * Generates AI video using Google Veo 3.1 via Vertex AI.
 * Handles long-running operations with automatic polling and video download.
 *
 * Usage:
 *   npx ts-node veo-generate.ts --prompt "your prompt" --output ./video.mp4
 *
 * Environment:
 *   GOOGLE_CLOUD_PROJECT - GCP project ID
 *   GOOGLE_CLOUD_LOCATION - Region (default: us-central1)
 *   GOOGLE_APPLICATION_CREDENTIALS - Path to service account JSON
 */

import * as fs from 'fs'
import * as path from 'path'
import * as https from 'https'
import { execFileSync } from 'child_process'

// ============================================================================
// Types
// ============================================================================

interface VeoConfig {
  prompt: string
  aspectRatio?: '16:9' | '9:16'
  durationSeconds?: 4 | 6 | 8
  resolution?: '720p' | '1080p'
  generateAudio?: boolean
  sampleCount?: number
  seed?: number
  model?: 'veo-3.1-generate-001' | 'veo-3.1-fast-generate-001'
}

interface GenerationResult {
  success: boolean
  videoPath?: string
  videoUrl?: string
  operationId?: string
  error?: string
  prompt: string
  settings: {
    model: string
    aspectRatio: string
    durationSeconds: number
    resolution: string
    generateAudio: boolean
  }
  generatedAt: Date
  processingTimeMs?: number
}

interface OperationStatus {
  done: boolean
  error?: { code: number; message: string }
  response?: {
    // Veo 3.1 response format
    generatedVideos?: Array<{
      video?: { uri: string }
      encoding?: string
    }>
    // Alternative response format (per some API versions)
    videos?: Array<{
      gcsUri?: string
      bytesBase64Encoded?: string
      mimeType?: string
    }>
    raiMediaFilteredCount?: number
  }
}

// ============================================================================
// Configuration
// ============================================================================

const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT || process.env.GOOGLE_CLOUD_PROJECT_ID
const LOCATION = process.env.GOOGLE_CLOUD_LOCATION || 'us-central1'
const CREDENTIALS_PATH = process.env.GOOGLE_APPLICATION_CREDENTIALS

const DEFAULT_CONFIG: Required<Omit<VeoConfig, 'prompt' | 'seed'>> = {
  aspectRatio: '16:9',
  durationSeconds: 8,
  resolution: '720p',
  generateAudio: false,
  sampleCount: 1,
  model: 'veo-3.1-generate-001',
}

const POLL_INTERVAL_MS = 10000 // 10 seconds
const MAX_POLL_ATTEMPTS = 60 // 10 minutes max

// ============================================================================
// Authentication
// ============================================================================

function getAccessToken(): string {
  if (!CREDENTIALS_PATH) {
    throw new Error(
      'GOOGLE_APPLICATION_CREDENTIALS environment variable not set.\n' +
      'Set it to the path of your service account JSON key file.'
    )
  }

  if (!fs.existsSync(CREDENTIALS_PATH)) {
    throw new Error(
      `Service account file not found: ${CREDENTIALS_PATH}\n` +
      'Ensure the file exists and GOOGLE_APPLICATION_CREDENTIALS points to it.'
    )
  }

  try {
    // Use gcloud to get access token (requires gcloud CLI)
    // Using execFileSync for security - no shell injection possible
    const token = execFileSync('gcloud', ['auth', 'application-default', 'print-access-token'], {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim()
    return token
  } catch {
    // Fallback: try to use the service account directly via gcloud
    try {
      execFileSync('gcloud', ['auth', 'activate-service-account', `--key-file=${CREDENTIALS_PATH}`], {
        stdio: 'pipe',
      })
      const token = execFileSync('gcloud', ['auth', 'print-access-token'], {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      }).trim()
      return token
    } catch (e) {
      throw new Error(
        'Failed to get access token. Ensure gcloud CLI is installed and configured.\n' +
        'Run: gcloud auth application-default login\n' +
        `Error: ${e instanceof Error ? e.message : String(e)}`
      )
    }
  }
}

// ============================================================================
// API Helpers
// ============================================================================

function makeRequest<T>(
  method: string,
  url: string,
  token: string,
  body?: object
): Promise<T> {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url)

    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    }

    const req = https.request(options, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data)
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`API Error ${res.statusCode}: ${JSON.stringify(parsed)}`))
          } else {
            resolve(parsed as T)
          }
        } catch {
          reject(new Error(`Failed to parse response: ${data}`))
        }
      })
    })

    req.on('error', reject)

    if (body) {
      req.write(JSON.stringify(body))
    }

    req.end()
  })
}

async function downloadFile(url: string, outputPath: string, token: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url)

    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }

    const file = fs.createWriteStream(outputPath)

    https.get(options, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        // Follow redirect
        const redirectUrl = res.headers.location
        if (redirectUrl) {
          downloadFile(redirectUrl, outputPath, token).then(resolve).catch(reject)
          return
        }
      }

      res.pipe(file)
      file.on('finish', () => {
        file.close()
        resolve()
      })
    }).on('error', (err) => {
      fs.unlink(outputPath, () => {}) // Delete partial file
      reject(err)
    })
  })
}

// ============================================================================
// Video Generation
// ============================================================================

async function submitGeneration(config: VeoConfig, token: string): Promise<string> {
  if (!PROJECT_ID) {
    throw new Error(
      'GOOGLE_CLOUD_PROJECT environment variable not set.\n' +
      'Set it to your GCP project ID.'
    )
  }

  const model = config.model || DEFAULT_CONFIG.model
  const endpoint = `https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/publishers/google/models/${model}:predictLongRunning`

  const requestBody = {
    instances: [{
      prompt: config.prompt,
    }],
    parameters: {
      aspectRatio: config.aspectRatio || DEFAULT_CONFIG.aspectRatio,
      durationSeconds: config.durationSeconds || DEFAULT_CONFIG.durationSeconds,
      resolution: config.resolution || DEFAULT_CONFIG.resolution,
      generateAudio: config.generateAudio ?? DEFAULT_CONFIG.generateAudio,
      sampleCount: config.sampleCount || DEFAULT_CONFIG.sampleCount,
      ...(config.seed !== undefined && { seed: config.seed }),
    },
  }

  console.log('\n🎬 Submitting video generation request...')
  console.log(`   Model: ${model}`)
  console.log(`   Prompt: "${config.prompt.substring(0, 80)}${config.prompt.length > 80 ? '...' : ''}"`)

  const response = await makeRequest<{ name: string }>(
    'POST',
    endpoint,
    token,
    requestBody
  )

  if (!response.name) {
    throw new Error('No operation name returned from API')
  }

  // Extract operation ID from full name
  const operationId = response.name.split('/').pop() || response.name
  console.log(`   Operation ID: ${operationId}`)

  return response.name
}

async function pollOperation(operationName: string, token: string): Promise<OperationStatus> {
  // Use fetchPredictOperation endpoint for generative AI models
  // Extract model path from operation name: projects/PROJECT/locations/LOC/publishers/google/models/MODEL/operations/OP_ID
  const modelPath = operationName.split('/operations/')[0]
  const endpoint = `https://${LOCATION}-aiplatform.googleapis.com/v1/${modelPath}:fetchPredictOperation`

  let attempts = 0

  while (attempts < MAX_POLL_ATTEMPTS) {
    attempts++

    const status = await makeRequest<OperationStatus>('POST', endpoint, token, { operationName })

    if (status.done) {
      return status
    }

    const elapsed = attempts * POLL_INTERVAL_MS / 1000
    process.stdout.write(`\r   Generating... (${elapsed}s elapsed)`)

    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS))
  }

  throw new Error(`Generation timed out after ${MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000} seconds`)
}

export async function generateVideo(
  config: VeoConfig,
  outputPath: string
): Promise<GenerationResult> {
  const startTime = Date.now()
  const settings = {
    model: config.model || DEFAULT_CONFIG.model,
    aspectRatio: config.aspectRatio || DEFAULT_CONFIG.aspectRatio,
    durationSeconds: config.durationSeconds || DEFAULT_CONFIG.durationSeconds,
    resolution: config.resolution || DEFAULT_CONFIG.resolution,
    generateAudio: config.generateAudio ?? DEFAULT_CONFIG.generateAudio,
  }

  try {
    // Get authentication token
    const token = getAccessToken()

    // Submit generation request
    const operationName = await submitGeneration(config, token)

    // Poll for completion
    console.log('\n   Waiting for generation to complete...')
    const status = await pollOperation(operationName, token)

    console.log('\n')

    // Check for errors
    if (status.error) {
      return {
        success: false,
        error: `Generation failed: ${status.error.message} (code: ${status.error.code})`,
        prompt: config.prompt,
        settings,
        operationId: operationName,
        generatedAt: new Date(),
        processingTimeMs: Date.now() - startTime,
      }
    }

    // Extract video - handle multiple response formats
    const generatedVideos = status.response?.generatedVideos
    const videos = status.response?.videos

    let videoUrl: string | undefined
    let videoBase64: string | undefined

    if (generatedVideos && generatedVideos.length > 0 && generatedVideos[0].video?.uri) {
      videoUrl = generatedVideos[0].video.uri
    } else if (videos && videos.length > 0) {
      if (videos[0].gcsUri) {
        videoUrl = videos[0].gcsUri
      } else if (videos[0].bytesBase64Encoded) {
        videoBase64 = videos[0].bytesBase64Encoded
      }
    }

    if (!videoUrl && !videoBase64) {
      // Debug: show actual response structure
      console.error('\n   Debug - Response structure:', JSON.stringify(status.response, null, 2))
      return {
        success: false,
        error: 'No video generated in response',
        prompt: config.prompt,
        settings,
        operationId: operationName,
        generatedAt: new Date(),
        processingTimeMs: Date.now() - startTime,
      }
    }

    // Save video
    console.log('   Saving video...')
    const resolvedPath = path.resolve(outputPath)
    const dir = path.dirname(resolvedPath)

    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }

    if (videoBase64) {
      // Decode base64 and write directly to file
      const videoBuffer = Buffer.from(videoBase64, 'base64')
      fs.writeFileSync(resolvedPath, videoBuffer)
    } else if (videoUrl) {
      // Download from URL
      await downloadFile(videoUrl, resolvedPath, token)
    }

    const processingTimeMs = Date.now() - startTime

    console.log('   Video generated successfully!')
    console.log(`   Saved to: ${resolvedPath}`)
    console.log(`   Processing time: ${(processingTimeMs / 1000).toFixed(1)}s`)

    return {
      success: true,
      videoPath: resolvedPath,
      videoUrl: videoUrl || 'base64-inline',
      operationId: operationName,
      prompt: config.prompt,
      settings,
      generatedAt: new Date(),
      processingTimeMs,
    }

  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      prompt: config.prompt,
      settings,
      generatedAt: new Date(),
      processingTimeMs: Date.now() - startTime,
    }
  }
}

// ============================================================================
// CLI
// ============================================================================

function printUsage(): void {
  console.log(`
Veo Video Generation

Usage:
  npx ts-node veo-generate.ts --prompt "your prompt" [options]

Required:
  --prompt, -p        The cinematic prompt for video generation

Options:
  --output, -o        Output file path (default: ./veo-output.mp4)
  --aspect-ratio      16:9 or 9:16 (default: 16:9)
  --duration          4, 6, or 8 seconds (default: 8)
  --resolution        720p or 1080p (default: 720p)
  --audio             Enable audio generation (default: false)
  --model             veo-3.1-generate-001 or veo-3.1-fast-generate-001
  --seed              Seed for reproducibility
  --samples           Number of videos to generate (1-4, default: 1)
  --help, -h          Show this help message

Environment Variables:
  GOOGLE_CLOUD_PROJECT              GCP project ID (required)
  GOOGLE_CLOUD_LOCATION             Region (default: us-central1)
  GOOGLE_APPLICATION_CREDENTIALS    Path to service account JSON (required)

Examples:
  # Hero background
  npx ts-node veo-generate.ts \\
    --prompt "Slow dolly through data particles, seamless loop, locked camera" \\
    --duration 4 \\
    --output ./hero.mp4

  # Marketing video with audio
  npx ts-node veo-generate.ts \\
    --prompt "Dynamic orbit around floating product, dramatic lighting" \\
    --resolution 1080p \\
    --audio \\
    --output ./product.mp4
`)
}

function parseArgs(args: string[]): { config: VeoConfig; output: string } | null {
  const config: VeoConfig = { prompt: '' }
  let output = './veo-output.mp4'

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    const next = args[i + 1]

    switch (arg) {
      case '--help':
      case '-h':
        printUsage()
        return null

      case '--prompt':
      case '-p':
        config.prompt = next || ''
        i++
        break

      case '--output':
      case '-o':
        output = next || output
        i++
        break

      case '--aspect-ratio':
        if (next === '16:9' || next === '9:16') {
          config.aspectRatio = next
        }
        i++
        break

      case '--duration':
        const dur = parseInt(next, 10)
        if (dur === 4 || dur === 6 || dur === 8) {
          config.durationSeconds = dur
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

      case '--model':
        if (next === 'veo-3.1-generate-001' || next === 'veo-3.1-fast-generate-001') {
          config.model = next
        }
        i++
        break

      case '--seed':
        config.seed = parseInt(next, 10)
        i++
        break

      case '--samples':
        const samples = parseInt(next, 10)
        if (samples >= 1 && samples <= 4) {
          config.sampleCount = samples
        }
        i++
        break
    }
  }

  if (!config.prompt) {
    console.error('Error: --prompt is required\n')
    printUsage()
    return null
  }

  return { config, output }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)

  if (args.length === 0) {
    printUsage()
    process.exit(0)
  }

  const parsed = parseArgs(args)
  if (!parsed) {
    process.exit(1)
  }

  const { config, output } = parsed

  console.log('\nVeo Video Generation')
  console.log('='.repeat(50))

  const result = await generateVideo(config, output)

  console.log('\n' + '='.repeat(50))

  if (result.success) {
    console.log('\nGeneration Summary:')
    console.log(`   Prompt: "${result.prompt.substring(0, 60)}${result.prompt.length > 60 ? '...' : ''}"`)
    console.log(`   Settings: ${result.settings.aspectRatio}, ${result.settings.durationSeconds}s, ${result.settings.resolution}`)
    console.log(`   Output: ${result.videoPath}`)
    console.log(`   Time: ${((result.processingTimeMs || 0) / 1000).toFixed(1)}s`)
    console.log('')
    process.exit(0)
  } else {
    console.error(`\nGeneration failed: ${result.error}`)
    process.exit(1)
  }
}

// Run if executed directly
main().catch((err) => {
  console.error('Fatal error:', err)
  process.exit(1)
})
