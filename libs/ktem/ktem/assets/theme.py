from typing import Iterable

from gradio.themes import Soft
from gradio.themes.utils import colors, fonts, sizes

apple_gray = colors.Color(
    name="apple_gray",
    c50="#f5f5f7",
    c100="#ebebed",
    c200="#e3e3e6",
    c300="#d2d2d7",
    c400="#b7b7bf",
    c500="#86868b",
    c600="#6e6e73",
    c700="#515154",
    c800="#2f2f32",
    c900="#1d1d1f",
    c950="#111113",
)

apple_blue = colors.Color(
    name="apple_blue",
    c50="#eff6ff",
    c100="#dbeafe",
    c200="#bfdbfe",
    c300="#93c5fd",
    c400="#60a5fa",
    c500="#0071e3",
    c600="#005cc8",
    c700="#004aa5",
    c800="#003b85",
    c900="#002f6a",
    c950="#00214a",
)

apple_slate = colors.Color(
    name="apple_slate",
    c50="#f8fafc",
    c100="#f1f5f9",
    c200="#e2e8f0",
    c300="#cbd5e1",
    c400="#94a3b8",
    c500="#64748b",
    c600="#475569",
    c700="#334155",
    c800="#1e293b",
    c900="#0f172a",
    c950="#020617",
)

surface_shadow = "0 1px 2px rgba(15,23,42,0.04), 0 14px 36px rgba(15,23,42,0.08)"
surface_shadow_lg = (
    "0 1px 2px rgba(15,23,42,0.06), 0 20px 44px rgba(15,23,42,0.14)"
)

err = "#d92d20"
err_hover = "#b42318"
err_dark = "#ff6961"
err_dark_hover = "#ff847d"

common = dict(
    color_accent="*primary_500",
    shadow_drop=surface_shadow,
    shadow_drop_lg=surface_shadow_lg,
    block_label_margin="*spacing_lg",
    block_label_padding="*spacing_lg",
    block_label_shadow="none",
    layout_gap="*spacing_lg",
    section_header_text_size="*text_lg",
    button_shadow="none",
    button_shadow_active="none",
    button_shadow_hover="none",
)

dark_mode = dict(
    body_text_color_subdued_dark="*neutral_400",
    background_fill_secondary_dark="#141416",
    border_color_accent_dark="rgba(255,255,255,0)",
    border_color_primary_dark="#2a2a2e",
    color_accent_soft_dark="#1f2a44",
    link_text_color_dark="*primary_300",
    link_text_color_active_dark="*primary_200",
    link_text_color_visited_dark="*primary_400",
    block_label_background_fill_dark="#1c1c1f",
    block_label_border_width_dark="0px",
    block_label_text_color_dark="#f5f5f7",
    block_shadow_dark="none",
    block_title_text_color_dark="#f5f5f7",
    panel_border_width_dark="0px",
    checkbox_background_color_selected_dark="*primary_500",
    checkbox_border_color_focus_dark="*primary_500",
    checkbox_border_color_selected_dark="*primary_500",
    checkbox_label_background_fill_selected_dark="#273554",
    checkbox_label_text_color_selected_dark="#f5f5f7",
    error_border_color_dark=err_dark,
    error_text_color_dark="#fff5f5",
    error_icon_color_dark=err_dark,
    input_background_fill_dark="#1f1f23",
    input_border_color_dark="#34343a",
    input_border_color_focus_dark="#4a4a52",
    input_placeholder_color_dark="#8a8a94",
    loader_color_dark="*primary_300",
    slider_color_dark="*primary_400",
    stat_background_fill_dark="#1f2734",
    table_border_color_dark="#2a2a2e",
    table_even_background_fill_dark="#141416",
    table_odd_background_fill_dark="#1b1b1f",
    table_row_focus_dark="#25252b",
    button_primary_background_fill_dark="*primary_500",
    button_primary_background_fill_hover_dark="*primary_600",
    button_secondary_background_fill_dark="#242429",
    button_secondary_background_fill_hover_dark="#2d2d33",
    button_cancel_background_fill_dark=err_dark,
    button_cancel_background_fill_hover_dark=err_dark_hover,
)

light_mode = dict(
    background_fill_primary="#f5f5f7",
    background_fill_secondary="#f5f5f7",
    body_background_fill="#f5f5f7",
    body_text_color_subdued="*neutral_500",
    border_color_accent="rgba(255,255,255,0)",
    border_color_primary="#d2d2d7",
    color_accent_soft="#eef4ff",
    link_text_color="*primary_500",
    link_text_color_visited="*primary_700",
    block_label_border_width="0px",
    block_label_background_fill="#ffffff",
    block_label_text_color="#1d1d1f",
    block_shadow="none",
    block_title_text_color="#1d1d1f",
    panel_border_width="0px",
    checkbox_background_color_selected="*primary_500",
    checkbox_border_color_focus="*primary_500",
    checkbox_border_color_selected="*primary_500",
    checkbox_label_border_color="#bfd4ff",
    error_background_fill="#fff7f6",
    error_border_color=err,
    error_text_color="#3d0c02",
    input_background_fill="#ffffff",
    input_border_color="#d2d2d7",
    input_border_color_focus="#a7a7af",
    input_placeholder_color="#8a8a94",
    loader_color="*primary_500",
    slider_color="*primary_500",
    stat_background_fill="#eef4ff",
    table_even_background_fill="#ffffff",
    table_odd_background_fill="#f5f5f7",
    table_row_focus="#eef4ff",
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_600",
    button_secondary_background_fill="#f5f5f7",
    button_secondary_background_fill_hover="#ebebed",
    button_cancel_background_fill=err,
    button_cancel_background_fill_hover=err_hover,
    button_cancel_text_color="#ffffff",
)


class Maia(Soft):
    """
    Official theme of Maia.
    Public version: https://huggingface.co/spaces/lone17/maia
    """

    def __init__(
        self,
        *,
        primary_hue: colors.Color | str = apple_blue,
        secondary_hue: colors.Color | str = apple_slate,
        neutral_hue: colors.Color | str = apple_gray,
        spacing_size: sizes.Size | str = sizes.spacing_md,
        radius_size: sizes.Size | str = sizes.radius_lg,
        text_size: sizes.Size | str = sizes.text_md,
        font: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            "-apple-system",
            "BlinkMacSystemFont",
            "SF Pro Text",
            "SF Pro Display",
            "Helvetica Neue",
            "ui-sans-serif",
            "sans-serif",
        ),
        font_mono: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            "SF Mono",
            "Menlo",
            "Monaco",
            "Cascadia Mono",
            "ui-monospace",
            "monospace",
        ),
    ):
        super().__init__(
            primary_hue=primary_hue,
            secondary_hue=secondary_hue,
            neutral_hue=neutral_hue,
            spacing_size=spacing_size,
            radius_size=radius_size,
            text_size=text_size,
            font=font,
            font_mono=font_mono,
        )
        self.name = "maia"
        super().set(
            **common,
            **dark_mode,
            **light_mode,
        )
