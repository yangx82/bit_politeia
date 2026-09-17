# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
from PIL import Image
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.context import ContextBuilder
from app.agent.pipeline import _compact_messages_in_flight
from app.agent.tools import inspect_media
from app.utils.multimodal import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    build_multimodal_content_blocks,
    encode_image_to_base64,
    extract_video_keyframes,
    resolve_media_items,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_multimodal_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def create_dummy_image(file_path: str, size: tuple[int, int] = (100, 100), color: tuple[int, int, int] = (255, 0, 0), mode: str = "RGB"):
    img = Image.new(mode, size, color=color)
    img.save(file_path)
    return file_path


def create_dummy_video(file_path: str, num_frames: int = 15, size: tuple[int, int] = (160, 120), fps: int = 5):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(file_path, fourcc, fps, size)
    for i in range(num_frames):
        # Create a frame with shifting color
        frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        frame[:, :] = ((i * 15) % 256, (i * 30) % 256, (i * 45) % 256)
        out.write(frame)
    out.release()
    return file_path


def test_encode_image_to_base64(temp_dir):
    img_path = os.path.join(temp_dir, "sample.png")
    create_dummy_image(img_path, size=(200, 150), color=(0, 255, 0))

    data_uri = encode_image_to_base64(img_path)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 50

    # Test large image auto-resizing
    large_path = os.path.join(temp_dir, "large.jpg")
    create_dummy_image(large_path, size=(1600, 1200), color=(100, 100, 200))
    data_uri_large = encode_image_to_base64(large_path, max_dim=800)
    assert data_uri_large.startswith("data:image/jpeg;base64,")

    # Test RGBA conversion to RGB for JPEG target
    rgba_path = os.path.join(temp_dir, "trans.png")
    create_dummy_image(rgba_path, size=(80, 80), color=(255, 0, 0), mode="RGBA")
    data_uri_rgba = encode_image_to_base64(rgba_path)
    assert data_uri_rgba.startswith("data:image/png;base64,")


def test_extract_video_keyframes(temp_dir):
    vid_path = os.path.join(temp_dir, "sample.mp4")
    create_dummy_video(vid_path, num_frames=20, fps=5)

    keyframes = extract_video_keyframes(vid_path, max_frames=4, max_dim=320)
    assert len(keyframes) >= 1
    assert len(keyframes) <= 4

    for kf in keyframes:
        assert kf["type"] == "image_url"
        assert "image_url" in kf
        assert kf["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert "time_sec" in kf


def test_resolve_media_items(temp_dir):
    img1 = os.path.join(temp_dir, "test1.jpg")
    img2 = os.path.join(temp_dir, "test2.png")
    create_dummy_image(img1)
    create_dummy_image(img2)

    # 1. From explicit media list
    media_list = [
        {"path": img1, "mime": "image/jpeg"},
        {"url": "https://example.com/remote.png"},
    ]
    resolved = resolve_media_items(media_list, "hello")
    assert len(resolved) == 2
    assert resolved[0]["path"] == img1
    assert resolved[1]["url"] == "https://example.com/remote.png"

    # 2. From text containing regex pattern (saved locally at: ...)
    text = f"File received: image.png (saved locally at: {img2}) ready for analysis."
    resolved_text = resolve_media_items(None, text)
    assert len(resolved_text) == 1
    assert resolved_text[0]["path"] == img2

    # 3. Deduplication when item appears in both
    resolved_both = resolve_media_items([{"path": img2}], text)
    assert len(resolved_both) == 1


def test_build_multimodal_content_blocks(temp_dir):
    img_path = os.path.join(temp_dir, "block_test.jpg")
    create_dummy_image(img_path)

    media_items = [{"path": img_path}]
    blocks = build_multimodal_content_blocks("Please inspect this image", media_items)

    assert isinstance(blocks, list)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "Please inspect this image"
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_context_builder_multimodal(temp_dir):
    img_path = os.path.join(temp_dir, "ctx_img.png")
    create_dummy_image(img_path)

    builder = ContextBuilder()

    # 1. Without media: HumanMessage content should be string
    msgs_text = builder.build_messages(
        history=[],
        current_message="Hello without media",
    )
    last_msg = msgs_text[-1]
    assert isinstance(last_msg, HumanMessage)
    assert isinstance(last_msg.content, str)
    assert "Hello without media" in last_msg.content

    # 2. With media: HumanMessage content should be list of dicts
    msgs_multimodal = builder.build_messages(
        history=[],
        current_message="Check this picture",
        media=[{"path": img_path, "mime": "image/png"}],
    )
    last_msg_mm = msgs_multimodal[-1]
    assert isinstance(last_msg_mm, HumanMessage)
    assert isinstance(last_msg_mm.content, list)
    assert len(last_msg_mm.content) >= 2
    assert last_msg_mm.content[0]["type"] == "text"
    assert "Check this picture" in last_msg_mm.content[0]["text"]
    assert last_msg_mm.content[1]["type"] == "image_url"


def test_compact_messages_in_flight_preserves_multimodal():
    # Construct a multimodal HumanMessage with a very long text block and an image_url block
    long_text = "Analysis report: " + ("ABCDE " * 400)
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ..."},
    }
    mm_msg = HumanMessage(content=[{"type": "text", "text": long_text}, image_block])

    compacted = _compact_messages_in_flight([mm_msg], aggressiveness=1)
    assert len(compacted) == 1
    res_msg = compacted[0]
    assert isinstance(res_msg.content, list)
    assert len(res_msg.content) == 2
    # Text block should be truncated
    assert res_msg.content[0]["type"] == "text"
    assert "truncated" in res_msg.content[0]["text"]
    # Image block must remain intact
    assert res_msg.content[1]["type"] == "image_url"
    assert res_msg.content[1]["image_url"]["url"] == image_block["image_url"]["url"]


@pytest.mark.asyncio
async def test_inspect_media_tool_image(temp_dir):
    img_path = os.path.join(temp_dir, "tool_img.jpg")
    create_dummy_image(img_path)

    # Mock agent_service LLM
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="I see a solid blue image.")

    with patch("app.services.agent_service.agent_service.raw_llm", mock_llm):
        result = await inspect_media.ainvoke({"file_path": img_path, "instruction": "What do you see?"})
        assert "Visual Analysis" in result
        assert "I see a solid blue image." in result
        assert mock_llm.ainvoke.called

        # Verify the payload passed to LLM has image_url
        call_args = mock_llm.ainvoke.call_args[0][0]
        assert isinstance(call_args[0], HumanMessage)
        assert isinstance(call_args[0].content, list)
        assert call_args[0].content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_inspect_media_tool_video(temp_dir):
    vid_path = os.path.join(temp_dir, "tool_vid.mp4")
    create_dummy_video(vid_path, num_frames=15, fps=5)

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content="Video contains shifting color frames.")

    with patch("app.services.agent_service.agent_service.raw_llm", mock_llm):
        result = await inspect_media.ainvoke({"file_path": vid_path, "instruction": "Summarize video"})
        assert "Visual Analysis" in result
        assert "Video contains shifting color frames." in result
        assert mock_llm.ainvoke.called

        call_args = mock_llm.ainvoke.call_args[0][0]
        assert isinstance(call_args[0], HumanMessage)
        # Should have text block + several image_url blocks
        assert len(call_args[0].content) >= 2
        assert call_args[0].content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_inspect_media_tool_error_handling(temp_dir):
    # 1. Non-existent file
    res_not_found = await inspect_media.ainvoke({"file_path": os.path.join(temp_dir, "non_existent.png")})
    assert "Error: Media file not found" in res_not_found

    # 2. Unsupported format
    txt_file = os.path.join(temp_dir, "doc.txt")
    with open(txt_file, "w") as f:
        f.write("text content")
    res_unsupported = await inspect_media.ainvoke({"file_path": txt_file})
    assert "Error: Unsupported media format" in res_unsupported

    # 3. LLM 429 / Throttled / Exception handling
    img_path = os.path.join(temp_dir, "err_img.png")
    create_dummy_image(img_path)

    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = Exception("429 Too Many Requests (Rate limit exceeded)")

    with patch("app.services.agent_service.agent_service.raw_llm", mock_llm):
        res_error = await inspect_media.ainvoke({"file_path": img_path})
        assert "Error during multimodal inspection" in res_error
        assert "429 Too Many Requests" in res_error
