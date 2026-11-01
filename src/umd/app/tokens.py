"""Design tokens taken from the V1.1 window prototype and architecture §10.4.

Values are logical CSS pixels. They are not a claim of pixel identity with
macOS Finder or Photos.
"""

from __future__ import annotations

LIGHT = {
    "window_bg": "#FFFFFF",
    "canvas": "#FFFFFF",
    "toolbar": "#F7F7F8",
    "sidebar": "#F4F5F8",
    "border": "#E4E5EA",
    "text": "#232329",
    "title": "#232329",
    "muted": "#8E8F97",
    "pill": "#F1F2F4",
    "accent": "#007AFF",
    "accent_text": "#116BEA",
    "hover": "#F0F1F4",
    "status_bg": "#FBFBFC",
    "inspector_bg": "#F8F9FB",
    "field": "#F3F3F6",
    "danger": "#E81123",
}

DARK = {
    "window_bg": "#1B1C20",
    "canvas": "#1B1C20",
    "toolbar": "#222328",
    "sidebar": "#1F2128",
    "border": "#34353C",
    "text": "#E5E5E9",
    "title": "#F5F5F7",
    "muted": "#A7A8B0",
    "pill": "#303138",
    "accent": "#0A84FF",
    "accent_text": "#79B5FF",
    "hover": "#2C2E36",
    "status_bg": "#202126",
    "inspector_bg": "#23242B",
    "field": "#303138",
    "danger": "#E81123",
}

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"
SIDEBAR_WIDTH = 236
SIDEBAR_WIDTH_COMPACT = 196
TOOLBAR_HEIGHT = 60
INSPECTOR_WIDTH = 298
INSPECTOR_WIDTH_COMPACT = 265
CONTENT_PADDING = 35
RADIUS_FIELD = 10
RADIUS_CARD = 12
RADIUS_PILL = 10
SPACE = (4, 8, 12, 16, 20, 24)
BREAKPOINT_COMPACT = 1100
COLUMNS_REGULAR = 4
COLUMNS_COMPACT = 3
