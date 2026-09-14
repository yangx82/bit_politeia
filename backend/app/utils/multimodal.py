"""Multimodal utilities for encoding images and extracting video frames for LLMs (e.g. Qwen3.7-Plus).

Handles:
- Image loading, downsampling, base64 encoding (JPEG/PNG/WEBP)
- Video keyframe extraction using OpenCV with temporal spacing and downsampling
- Automatic detection of media paths from InboundMessage and message text
"""

import base64
import io
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# Regex to detect Feishu/Telegram system paths like: (saved locally at: /path/to/file.ext)
SAVED_LOCALLY_REGEX = re.compile(
    r"(?:saved locally at|file saved at|downloaded to):\s*([^\r\n\)]+)", re.IGNORECASE
)


def encode_image_to_base64(
    image_path: str | Path,
    max_dimension: int = 1024,
    quality: int = 85,
    max_dim: int | None = None,
) -> str | None:
    """Load an image, downscale if larger than max_dimension, and return as a Base64 data URI.

    Args:
        image_path: Local path to the image file.
        max_dimension: Maximum width or height in pixels.
        quality: JPEG compression quality (1-100).
        max_dim: Alias for max_dimension.

    Returns:
        Data URI string 'data:image/jpeg;base64,...' or None on failure.
    """
    if max_dim is not None:
        max_dimension = max_dim
    path = Path(image_path)
    if not path.is_file():
        logger.warning(f"[Multimodal] Image file not found: {image_path}")
        return None

    try:
        from PIL import Image

        with Image.open(path) as img:
            # Preserve format based on extension and transparency
            is_transparent = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )
            ext = path.suffix.lower()
            if is_transparent or ext == ".png":
                target_format = "PNG"
                mime_type = "image/png"
            elif ext == ".webp":
                target_format = "WEBP"
                mime_type = "image/webp"
            else:
                target_format = "JPEG"
                mime_type = "image/jpeg"

            if target_format == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")

            # Downsample if needed
            w, h = img.size
            if max(w, h) > max_dimension:
                scale = max_dimension / max(w, h)
                new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                logger.debug(
                    f"[Multimodal] Resized image {path.name} from ({w}, {h}) to ({new_w}, {new_h})"
                )

            buffer = io.BytesIO()
            if target_format == "JPEG":
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
            elif target_format == "WEBP":
                img.save(buffer, format="WEBP", quality=quality)
            else:
                img.save(buffer, format="PNG", optimize=True)

            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:{mime_type};base64,{b64_str}"

    except Exception as e:
        logger.error(f"[Multimodal] Error encoding image {image_path}: {e}")
        return None


def extract_video_keyframes(
    video_path: str | Path,
    max_frames: int = 6,
    max_dimension: int = 720,
    quality: int = 80,
    max_dim: int | None = None,
) -> list[dict[str, Any]]:
    """Sample keyframes evenly across a video and encode as Base64 JPEG payloads.

    Args:
        video_path: Path to local video file.
        max_frames: Maximum number of frames to extract (default 6).
        max_dimension: Max pixel width/height per frame.
        quality: JPEG compression quality for frames.
        max_dim: Alias for max_dimension.

    Returns:
        List of dicts formatted for OpenAI image_url with timestamp metadata:
        [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}, "time_sec": 1.5}, ...]
    """
    if max_dim is not None:
        max_dimension = max_dim
    path = Path(video_path)
    if not path.is_file():
        logger.warning(f"[Multimodal] Video file not found: {video_path}")
        return []

    try:
        import cv2
        from PIL import Image

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            logger.error(f"[Multimodal] OpenCV could not open video: {video_path}")
            return []

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        duration_sec = total_frames / fps if total_frames > 0 else 0.0

        if total_frames <= 0:
            cap.release()
            return []

        num_samples = min(max_frames, max(1, total_frames))
        # Pick evenly spaced frame indices, avoiding boundary 0 if multiple
        if num_samples == 1:
            frame_indices = [total_frames // 2]
        else:
            step = total_frames / (num_samples + 1)
            frame_indices = [int(step * (i + 1)) for i in range(num_samples)]

        results = []
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            time_sec = round(idx / fps, 1)

            # Convert BGR (OpenCV) to RGB (PIL)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)

            # Downsample if needed
            w, h = img.size
            if max(w, h) > max_dimension:
                scale = max_dimension / max(w, h)
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64_str}"

            results.append({
                "type": "image_url",
                "image_url": {
                    "url": data_uri,
                    "detail": "auto",
                },
                "time_sec": time_sec,
            })

        cap.release()
        logger.info(
            f"[Multimodal] Extracted {len(results)} frames from {path.name} (duration: {duration_sec:.1f}s)"
        )
        return results

    except Exception as e:
        logger.error(f"[Multimodal] Error extracting video frames from {video_path}: {e}", exc_info=True)
        return []


def resolve_media_items(
    media_list: list[dict[str, Any]] | None = None,
    text_content: str = "",
) -> list[dict[str, Any]]:
    """Extract and validate media items from explicit media metadata and text patterns.

    Returns normalized list of dicts:
    [{"type": "image"|"video", "path": "/path/to/file", "name": "file.jpg"}, ...]
    """
    resolved = []
    seen_paths = set()

    # 1. Process explicit media list from InboundMessage.media
    if media_list:
        for item in media_list:
            if not isinstance(item, dict):
                continue
            raw_path = item.get("path")
            raw_url = item.get("url")

            if raw_path:
                clean_path = Path(raw_path).resolve()
                if clean_path.exists() and str(clean_path) not in seen_paths:
                    ext = clean_path.suffix.lower()
                    m_type = item.get("type")
                    if not m_type:
                        m_type = "image" if ext in IMAGE_EXTENSIONS else ("video" if ext in VIDEO_EXTENSIONS else "file")

                    if m_type in ("image", "video"):
                        resolved.append({
                            "type": m_type,
                            "path": str(clean_path),
                            "name": item.get("name", clean_path.name),
                        })
                        seen_paths.add(str(clean_path))
            elif raw_url and str(raw_url) not in seen_paths:
                m_type = item.get("type")
                if not m_type:
                    ext = Path(raw_url.split("?")[0]).suffix.lower()
                    m_type = "video" if ext in VIDEO_EXTENSIONS else "image"
                resolved.append({
                    "type": m_type,
                    "url": raw_url,
                    "name": item.get("name", raw_url.split("/")[-1]),
                })
                seen_paths.add(str(raw_url))

    # 2. Extract potential paths mentioned in system text (e.g. Feishu download pattern)
    if text_content and isinstance(text_content, str):
        matches = SAVED_LOCALLY_REGEX.findall(text_content)
        for m in matches:
            candidate = Path(m.strip().strip('"\'')).resolve()
            if candidate.is_file() and str(candidate) not in seen_paths:
                ext = candidate.suffix.lower()
                if ext in IMAGE_EXTENSIONS:
                    resolved.append({
                        "type": "image",
                        "path": str(candidate),
                        "name": candidate.name,
                    })
                    seen_paths.add(str(candidate))
                elif ext in VIDEO_EXTENSIONS:
                    resolved.append({
                        "type": "video",
                        "path": str(candidate),
                        "name": candidate.name,
                    })
                    seen_paths.add(str(candidate))

    return resolved


def build_multimodal_content_blocks(
    text_message: str,
    media_items: list[dict[str, Any]],
    max_images: int = 8,
    max_video_frames: int = 6,
) -> list[dict[str, Any]] | str:
    """Build OpenAI/LangChain-compatible content blocks for HumanMessage.

    If media_items contains valid images or video frames, returns list of dicts:
    [{"type": "text", "text": ...}, {"type": "image_url", "image_url": ...}]
    Otherwise returns the original string unchanged.
    """
    if not media_items:
        return text_message

    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": text_message}
    ]

    images_added = 0
    for item in media_items:
        m_type = item.get("type")
        m_path = item.get("path")
        m_url = item.get("url")

        if not m_type:
            if m_path:
                ext = Path(m_path).suffix.lower()
                m_type = "video" if ext in VIDEO_EXTENSIONS else "image"
            elif m_url:
                ext = Path(m_url.split("?")[0]).suffix.lower()
                m_type = "video" if ext in VIDEO_EXTENSIONS else "image"

        if m_url:
            if images_added < max_images:
                blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": m_url,
                        "detail": "auto",
                    },
                })
                images_added += 1
            continue

        if not m_path or not os.path.exists(m_path):
            continue

        if m_type == "image":
            if images_added >= max_images:
                continue
            data_uri = encode_image_to_base64(m_path)
            if data_uri:
                blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_uri,
                        "detail": "auto",
                    },
                })
                images_added += 1

        elif m_type == "video":
            frames = extract_video_keyframes(m_path, max_frames=max_video_frames)
            for f in frames:
                t_sec = f.get("time_sec", 0.0)
                blocks.append({
                    "type": "text",
                    "text": f"[视频帧截取 t={t_sec}s]:",
                })
                blocks.append({
                    "type": "image_url",
                    "image_url": f["image_url"],
                })

    # If only text block was created because images failed to encode, return plain string
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return text_message

    return blocks
