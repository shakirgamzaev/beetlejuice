"""Automated parking spot boundary generation for camera feeds.

Solves initial zero-configuration setup for parking lots by automatically
detecting parking columns, painted stall dividers, and generating standardized
boundary boxes without requiring manual drawing of hundreds of spots.

Features:
- Full-lot auto-detection from camera snapshot (Canny + Top-Hat + Morphology + Peak Grid Lattice)
- Intelligent vegetation/grass masking to prevent false boundaries on landscaping
- Regularized bay generation ensuring equal stall widths and heights
- Two-click Bay/Column Generator tool for rapid manual column auto-fill
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger("auto_detect")


def detect_spots_from_frame(
    frame: np.ndarray,
    min_line_len: int = 14,
    max_line_len: int = 75,
) -> list[dict[str, Any]]:
    """Automatically detect all parking spot boundaries from a single camera frame.

    Returns a list of dicts with keys: 'spot_id', 'bbox', 'points'.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 1. Mask out vegetation / green grass (Hue 30-88, Saturation >= 35)
    is_grass = (hsv[:, :, 0] >= 30) & (hsv[:, :, 0] <= 88) & (hsv[:, :, 1] >= 35)

    # 2. Extract bright line markings using morphological Top-Hat transform
    tophat = cv2.morphologyEx(
        gray,
        cv2.MORPH_TOPHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
    )
    _, thresh = cv2.threshold(tophat, 20, 255, cv2.THRESH_BINARY)

    # 3. Horizontal line filter (parking dividers in vertical columns)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_line_len, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    h_lines[is_grass] = 0

    # 4. Vertical line filter (parking dividers in horizontal columns)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_line_len))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
    v_lines[is_grass] = 0

    h_count = cv2.countNonZero(h_lines)
    v_count = cv2.countNonZero(v_lines)

    # Primary orientation based on painted marking density
    if h_count >= v_count:
        return _detect_vertical_bays_horizontal_stalls(
            frame, h_lines, is_grass, min_line_len, max_line_len
        )
    else:
        return _detect_horizontal_bays_vertical_stalls(
            frame, v_lines, is_grass, min_line_len, max_line_len
        )


def _detect_vertical_bays_horizontal_stalls(
    frame: np.ndarray,
    line_mask: np.ndarray,
    is_grass: np.ndarray,
    min_line_len: int,
    max_line_len: int,
) -> list[dict[str, Any]]:
    """Detect vertical columns of stalls separated by horizontal painted lines."""
    h, w = frame.shape[:2]
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines: list[dict[str, float]] = []

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if min_line_len <= bw <= max_line_len and bh <= 10:
            lines.append({
                "x": float(x),
                "y": float(y),
                "w": float(bw),
                "h": float(bh),
                "cx": float(x + bw / 2),
                "cy": float(y + bh / 2),
            })

    if len(lines) < 6:
        return []

    # Project on X axis to identify column peaks
    x_proj = np.sum(line_mask > 0, axis=0).astype(np.float32)
    kernel_size = 15
    kernel = np.ones(kernel_size, dtype=np.float32) / kernel_size
    smoothed = np.convolve(x_proj, kernel, mode="same")

    raw_peaks: list[int] = []
    min_peak_val = max(10.0, float(np.percentile(smoothed, 70)))

    for i in range(15, w - 15):
        if smoothed[i] >= min_peak_val and smoothed[i] == max(smoothed[max(0, i - 7) : min(w, i + 8)]):
            raw_peaks.append(i)

    # Merge nearby peaks (distance < 18 px)
    peaks: list[int] = []
    for p in sorted(raw_peaks):
        if not peaks:
            peaks.append(p)
        elif p - peaks[-1] < 18:
            if smoothed[p] > smoothed[peaks[-1]]:
                peaks[-1] = p
        else:
            peaks.append(p)

    spots: list[dict[str, Any]] = []
    spot_index = 1

    for peak_x in peaks:
        col_lines = [l for l in lines if abs(l["cx"] - peak_x) <= 20]
        if len(col_lines) < 3:
            continue

        col_lines.sort(key=lambda l: l["cy"])

        med_w = int(np.median([l["w"] for l in col_lines]))
        med_x = int(np.median([l["x"] for l in col_lines]))

        cys = [l["cy"] for l in col_lines]
        diffs = [cys[i + 1] - cys[i] for i in range(len(cys) - 1)]
        valid_diffs = [d for d in diffs if 9 <= d <= 32]

        stall_h = float(np.median(valid_diffs)) if valid_diffs else 16.0
        start_y = min(cys)
        end_y = max(cys)

        curr_y = start_y
        while curr_y + stall_h <= end_y + stall_h * 0.5:
            sy = int(round(curr_y))
            sh = int(round(stall_h))

            # Quality checks: not grass, and has nearby physical lines
            y1, y2 = max(0, sy), min(h, sy + sh)
            x1, x2 = max(0, med_x), min(w, med_x + med_w)
            grass_ratio = float(np.mean(is_grass[y1:y2, x1:x2])) if (y2 > y1 and x2 > x1) else 1.0
            has_line_support = any(
                abs(l["cy"] - (curr_y + stall_h / 2)) <= stall_h * 1.8 for l in col_lines
            )

            if has_line_support and grass_ratio < 0.25:
                spots.append({
                    "spot_id": f"A-{spot_index}",
                    "bbox": [med_x, sy, med_w, sh],
                    "points": [
                        [med_x, sy],
                        [med_x + med_w, sy],
                        [med_x + med_w, sy + sh],
                        [med_x, sy + sh],
                    ],
                })
                spot_index += 1

            curr_y += stall_h

    # Sort spots geographically: columns left-to-right, spots top-to-bottom
    spots.sort(key=lambda s: (s["bbox"][0] // 30, s["bbox"][1]))
    # Re-index nicely
    for i, s in enumerate(spots, start=1):
        s["spot_id"] = f"A-{i}"

    return spots


def _detect_horizontal_bays_vertical_stalls(
    frame: np.ndarray,
    line_mask: np.ndarray,
    is_grass: np.ndarray,
    min_line_len: int,
    max_line_len: int,
) -> list[dict[str, Any]]:
    """Detect horizontal bays of stalls separated by vertical painted lines."""
    h, w = frame.shape[:2]
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines: list[dict[str, float]] = []

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if min_line_len <= bh <= max_line_len and bw <= 10:
            lines.append({
                "x": float(x),
                "y": float(y),
                "w": float(bw),
                "h": float(bh),
                "cx": float(x + bw / 2),
                "cy": float(y + bh / 2),
            })

    if len(lines) < 6:
        return []

    y_proj = np.sum(line_mask > 0, axis=1).astype(np.float32)
    kernel_size = 15
    kernel = np.ones(kernel_size, dtype=np.float32) / kernel_size
    smoothed = np.convolve(y_proj, kernel, mode="same")

    raw_peaks: list[int] = []
    min_peak_val = max(10.0, float(np.percentile(smoothed, 70)))

    for i in range(15, h - 15):
        if smoothed[i] >= min_peak_val and smoothed[i] == max(smoothed[max(0, i - 7) : min(h, i + 8)]):
            raw_peaks.append(i)

    peaks: list[int] = []
    for p in sorted(raw_peaks):
        if not peaks:
            peaks.append(p)
        elif p - peaks[-1] < 18:
            if smoothed[p] > smoothed[peaks[-1]]:
                peaks[-1] = p
        else:
            peaks.append(p)

    spots: list[dict[str, Any]] = []
    spot_index = 1

    for peak_y in peaks:
        bay_lines = [l for l in lines if abs(l["cy"] - peak_y) <= 20]
        if len(bay_lines) < 3:
            continue

        bay_lines.sort(key=lambda l: l["cx"])

        med_h = int(np.median([l["h"] for l in bay_lines]))
        med_y = int(np.median([l["y"] for l in bay_lines]))

        cxs = [l["cx"] for l in bay_lines]
        diffs = [cxs[i + 1] - cxs[i] for i in range(len(cxs) - 1)]
        valid_diffs = [d for d in diffs if 9 <= d <= 32]

        stall_w = float(np.median(valid_diffs)) if valid_diffs else 16.0
        start_x = min(cxs)
        end_x = max(cxs)

        curr_x = start_x
        while curr_x + stall_w <= end_x + stall_w * 0.5:
            sx = int(round(curr_x))
            sw = int(round(stall_w))

            y1, y2 = max(0, med_y), min(h, med_y + med_h)
            x1, x2 = max(0, sx), min(w, sx + sw)
            grass_ratio = float(np.mean(is_grass[y1:y2, x1:x2])) if (y2 > y1 and x2 > x1) else 1.0
            has_line_support = any(
                abs(l["cx"] - (curr_x + stall_w / 2)) <= stall_w * 1.8 for l in bay_lines
            )

            if has_line_support and grass_ratio < 0.25:
                spots.append({
                    "spot_id": f"A-{spot_index}",
                    "bbox": [sx, med_y, sw, med_h],
                    "points": [
                        [sx, med_y],
                        [sx + sw, med_y],
                        [sx + sw, med_y + med_h],
                        [sx, med_y + med_h],
                    ],
                })
                spot_index += 1

            curr_x += stall_w

    spots.sort(key=lambda s: (s["bbox"][1] // 30, s["bbox"][0]))
    for i, s in enumerate(spots, start=1):
        s["spot_id"] = f"A-{i}"

    return spots


def generate_column_bay(
    p1: tuple[int, int],
    p2: tuple[int, int],
    spot_height: int = 16,
    spot_width: int | None = None,
    start_index: int = 1,
) -> list[dict[str, Any]]:
    """Two-click bay generator: click top-left and bottom-right of a column.

    Automatically subdivides the vertical bay into evenly-spaced parking spots.
    """
    x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
    x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])

    w = spot_width if spot_width is not None else (x2 - x1)
    total_h = y2 - y1

    if total_h <= 0 or w <= 0:
        return []

    # Calculate number of stalls
    count = max(1, int(round(total_h / max(1, spot_height))))
    exact_h = total_h / count

    spots = []
    for i in range(count):
        sy = int(round(y1 + i * exact_h))
        sh = int(round(exact_h))
        spots.append({
            "spot_id": f"A-{start_index + i}",
            "bbox": [x1, sy, w, sh],
            "points": [
                [x1, sy],
                [x1 + w, sy],
                [x1 + w, sy + sh],
                [x1, sy + sh],
            ],
        })
    return spots


def draw_candidate_overlay(
    frame: np.ndarray,
    candidates: list[dict[str, Any]],
) -> np.ndarray:
    """Render candidates with an amber review overlay and count banner."""
    vis = frame.copy()
    overlay = vis.copy()

    for s in candidates:
        pts = np.array(s["points"], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 215, 255))  # Gold / Amber fill
        cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 255), thickness=1)

    # 35% translucent blend
    cv2.addWeighted(overlay, 0.35, vis, 0.65, 0, vis)
    return vis

