"""Motion tokens. Durations are milliseconds. Spring fields map to Qt Quick SpringAnimation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionToken:
    name: str
    duration_ms: int
    spring: float | None
    damping: float | None
    mass: float | None
    amplitude: float | None
    cancel_policy: str
    reduced_motion: str


TOKENS: dict[str, MotionToken] = {
    "button_hover": MotionToken(
        "button_hover", 110, None, None, None, None, "retarget", "opacity-only"
    ),
    "button_press": MotionToken(
        "button_press", 100, None, None, None, None, "retarget", "none"
    ),
    "sidebar_select": MotionToken(
        "sidebar_select", 180, None, None, None, None, "retarget", "instant"
    ),
    "inspector": MotionToken(
        "inspector", 300, 2.4, 0.78, 1.0, 0.0, "retarget", "instant"
    ),
    "popover": MotionToken(
        "popover", 180, None, None, None, 0.03, "retarget", "fade"
    ),
    "preview": MotionToken(
        "preview", 260, None, None, None, None, "retarget", "fade"
    ),
    "thumbnail_in": MotionToken(
        "thumbnail_in", 150, None, None, None, None, "drop", "none"
    ),
    "grid_select": MotionToken(
        "grid_select", 170, None, None, None, None, "retarget", "instant"
    ),
    "success": MotionToken(
        "success", 190, 2.0, 0.86, 0.8, 0.0, "retarget", "instant"
    ),
}


def token(name: str) -> MotionToken:
    return TOKENS[name]
