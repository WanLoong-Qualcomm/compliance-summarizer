"""Deterministic image assets for the v0.1 report."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .analytics import FailureAnalysisResult
from .contracts import CaseAnalysis


_DISPLAY_HEADERS: tuple[str, ...] = (
    "Worksheet row",
    "LNAMODE",
    "CAMODE",
    "STD",
    "BAND",
    "BW",
    "MEASPORT",
    "DLP",
    "DIV",
    "F0_MHZ",
    "TESTNAME",
    "GAINMODE",
    "BBPATH",
    "FREQ",
    "CHANNEL",
    "Result?",
    "LL",
    "UL",
)

_BACKGROUND = (255, 255, 255)
_TEXT = (24, 24, 27)
_HEADER_BACKGROUND = (31, 78, 121)
_HEADER_TEXT = (255, 255, 255)
_ALTERNATE_ROW_BACKGROUND = (239, 245, 251)
_GRID = (170, 180, 190)
_EMPTY_BACKGROUND = (248, 249, 251)
_PADDING = 12
_CELL_PADDING = 6
_ROW_HEIGHT = 26
_TITLE_HEIGHT = 42
_EMPTY_IMAGE_SIZE = (760, 140)


@dataclass(frozen=True, slots=True)
class TopFailureTableImage:
    """An inline-ready PNG and the values used to create it."""

    selected_pivot: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    data_uri: str
    empty_state_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.selected_pivot, str) or not self.selected_pivot.strip():
            raise ValueError("selected_pivot must be a nonempty string")
        if self.selected_pivot != self.selected_pivot.strip():
            raise ValueError("selected_pivot must be trimmed")
        columns = tuple(self.columns)
        rows = tuple(tuple(row) for row in self.rows)
        if not columns:
            raise ValueError("columns must not be empty")
        if any(not isinstance(column, str) or not column for column in columns):
            raise ValueError("columns must contain nonempty strings")
        if any(len(row) != len(columns) for row in rows):
            raise ValueError("every image row must match the column count")
        if any(not isinstance(value, str) for row in rows for value in row):
            raise TypeError("image row values must be strings")
        if len(rows) > 50:
            raise ValueError("an image cannot contain more than 50 data rows")
        if not self.data_uri.startswith("data:image/png;base64,"):
            raise ValueError("data_uri must be an inline PNG data URI")
        if not rows and not self.empty_state_message:
            raise ValueError("empty images must include an empty-state message")
        if rows and self.empty_state_message is not None:
            raise ValueError("non-empty images must not include an empty-state message")
        if self.empty_state_message is not None and not isinstance(
            self.empty_state_message, str
        ):
            raise TypeError("empty_state_message must be a string or None")
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", rows)

    @property
    def is_empty(self) -> bool:
        """Whether the image represents the explicit empty state."""

        return not self.rows

    @property
    def image_data_uri(self) -> str:
        """Compatibility name for callers that call the asset an image URI."""

        return self.data_uri


def render_top_failure_table_image(
    failure_analysis: FailureAnalysisResult,
    selected_pivot: str,
) -> TopFailureTableImage:
    """Render the ranked top selected-pivot failures as an inline PNG.

    The image contains the same order as ``failure_analysis.top_failure_cases``
    and never more than the first 50 rankable cases.  Workbook values are
    displayed in full; missing values are represented explicitly as ``N/A``.
    """

    if not isinstance(failure_analysis, FailureAnalysisResult):
        raise TypeError("failure_analysis must be FailureAnalysisResult")
    _validate_selected_pivot(selected_pivot)

    source_cases = tuple(failure_analysis.top_failure_cases[:50])
    for case_analysis in source_cases:
        if case_analysis.selected_pivot != selected_pivot:
            raise ValueError(
                "top_failure_cases must use the configured selected pivot"
            )

    columns = _display_headers(selected_pivot)
    rows = tuple(
        _display_row(case_analysis, selected_pivot)
        for case_analysis in source_cases
    )
    empty_state_message = (
        f"No rankable failure cases for selected pivot '{selected_pivot}'."
        if not rows
        else None
    )
    image_bytes = _render_png(selected_pivot, columns, rows)
    data_uri = "data:image/png;base64," + b64encode(image_bytes).decode("ascii")
    return TopFailureTableImage(
        selected_pivot=selected_pivot,
        columns=columns,
        rows=rows,
        data_uri=data_uri,
        empty_state_message=empty_state_message,
    )


def generate_top_failure_table_image(
    failure_analysis: FailureAnalysisResult,
    selected_pivot: str,
) -> TopFailureTableImage:
    """Alias using the task's ``generate`` terminology."""

    return render_top_failure_table_image(failure_analysis, selected_pivot)


def _display_headers(selected_pivot: str) -> tuple[str, ...]:
    return _DISPLAY_HEADERS + (f"{selected_pivot} wcMargin",)


def _display_row(case_analysis: CaseAnalysis, selected_pivot: str) -> tuple[str, ...]:
    case = case_analysis.case
    values: list[str] = [str(case.worksheet_row_number)]
    for header in _DISPLAY_HEADERS[1:]:
        value = case.source_values.get(header, case.fixed_values.get(header))
        values.append(_display_value(value))
    values.append(_display_value(case_analysis.selected_margin))
    return tuple(values)


def _display_value(value: object) -> str:
    if value is None:
        return "N/A"
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _render_png(
    selected_pivot: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> bytes:
    font = _load_font(14)
    title_font = _load_font(16)
    if not rows:
        image = Image.new("RGB", _EMPTY_IMAGE_SIZE, _EMPTY_BACKGROUND)
        draw = ImageDraw.Draw(image)
        message = (
            f"No rankable failure cases for selected pivot '{selected_pivot}'."
        )
        draw.text(
            (_PADDING, _PADDING),
            message,
            fill=_TEXT,
            font=title_font,
        )
        return _encode_png(image)

    widths = _column_widths(columns, rows, font)
    image_width = sum(widths) + (_PADDING * 2)
    image_height = _TITLE_HEIGHT + _ROW_HEIGHT * (len(rows) + 1) + (_PADDING * 2)
    image = Image.new("RGB", (image_width, image_height), _BACKGROUND)
    draw = ImageDraw.Draw(image)

    title = f"Top {len(rows)} GAIN FAIL cases - {selected_pivot} wcMargin"
    draw.text((_PADDING, _PADDING), title, fill=_TEXT, font=title_font)

    header_top = _PADDING + _TITLE_HEIGHT
    _draw_row(
        draw,
        columns,
        widths,
        header_top,
        font=font,
        fill=_HEADER_BACKGROUND,
        text_fill=_HEADER_TEXT,
    )
    for index, row in enumerate(rows):
        row_top = header_top + _ROW_HEIGHT * (index + 1)
        fill = _ALTERNATE_ROW_BACKGROUND if index % 2 else _BACKGROUND
        _draw_row(
            draw,
            row,
            widths,
            row_top,
            font=font,
            fill=fill,
            text_fill=_TEXT,
        )
    return _encode_png(image)


def _column_widths(
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    font: ImageFont.ImageFont,
) -> tuple[int, ...]:
    widths: list[int] = []
    for column_index, column in enumerate(columns):
        values = (column,) + tuple(row[column_index] for row in rows)
        widest = max(_text_width(value, font) for value in values)
        widths.append(widest + _CELL_PADDING * 2)
    return tuple(widths)


def _draw_row(
    draw: ImageDraw.ImageDraw,
    values: Iterable[str],
    widths: tuple[int, ...],
    top: int,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    text_fill: tuple[int, int, int],
) -> None:
    left = _PADDING
    for value, width in zip(values, widths, strict=True):
        draw.rectangle(
            (left, top, left + width, top + _ROW_HEIGHT),
            fill=fill,
            outline=_GRID,
        )
        draw.text(
            (left + _CELL_PADDING, top + (_ROW_HEIGHT - _text_height(font)) // 2),
            value,
            fill=text_fill,
            font=font,
        )
        left += width


def _text_width(value: str, font: ImageFont.ImageFont) -> int:
    bbox = font.getbbox(value)
    return bbox[2] - bbox[0]


def _text_height(font: ImageFont.ImageFont) -> int:
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - retained for older Pillow releases
        return ImageFont.load_default()


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def _validate_selected_pivot(selected_pivot: str) -> None:
    if not isinstance(selected_pivot, str) or not selected_pivot.strip():
        raise ValueError("selected_pivot must be a nonempty string")
    if selected_pivot != selected_pivot.strip():
        raise ValueError("selected_pivot must be trimmed")
