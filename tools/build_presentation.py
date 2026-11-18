# /// script
# dependencies = ["python-pptx", "Pillow"]
# ///
"""Build editable presentations from JSON with local media and slide navigation."""

import argparse
import io
import json
import math
import mimetypes
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches, Pt


def build_presentation(
    source_path, output_path=None, *, preview_dir=None, font_dir=None
):
    """Render caller-selected JSON; resolve local assets beside source file."""
    SOURCE = Path(source_path).resolve()
    OUTPUT = (
        Path(output_path).resolve()
        if output_path is not None
        else SOURCE.with_suffix(".pptx")
    )
    if SOURCE == OUTPUT:
        raise ValueError("Output must differ from JSON source")
    CACHE = Path(preview_dir).resolve() if preview_dir is not None else None
    if CACHE is not None:
        CACHE.mkdir(parents=True, exist_ok=True)
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    W, H = 13.333333, 7.5
    BG = "F6F8FB"
    NAVY = "102D4D"
    INK = "15334E"
    MUTED = "52677A"
    TEAL = "007D88"
    CYAN = "63D8D0"
    LINE = "DCE5ED"
    WHITE = "FFFFFF"
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    prs.core_properties.title = data["slides"][0]["title"].replace("\n", " ")
    prs.core_properties.subject = data.get("purpose", "")
    prs.core_properties.author = data.get("author", "")
    prs.core_properties.keywords = data.get("status", "")
    prs.core_properties.comments = data.get("scope", "")
    render_pages = []
    overflow = []
    layout = []
    pending_links = []
    slide_by_id = {}
    media_records = []
    SCALE = 120
    font_cache = {}

    def font(sz, bold=False, mono=False):
        key = (sz, bold, mono)
        if key not in font_cache:
            name = (
                "consola.ttf" if mono else ("segoeuib.ttf" if bold else "segoeui.ttf")
            )
            fallback = (
                "DejaVuSansMono.ttf"
                if mono
                else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
            )
            candidates = []
            if font_dir is not None:
                candidates.append(str(Path(font_dir) / name))
            if os.name == "nt":
                candidates.append(
                    str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name)
                )
            candidates.extend((name, fallback))
            for candidate in candidates:
                try:
                    font_cache[key] = ImageFont.truetype(
                        candidate, round(sz * SCALE / 72)
                    )
                    break
                except OSError:
                    pass
            else:
                font_cache[key] = ImageFont.load_default(size=round(sz * SCALE / 72))
        return font_cache[key]

    def rgb(c):
        return RGBColor.from_string(c)

    def wrap(text, max_width, sz, bold=False, mono=False):
        f = font(sz, bold, mono)
        result = []
        for p in text.split("\n"):
            current = ""
            for word in p.split(" "):
                trial = (current + " " + word).strip()
                if f.getlength(trial) > max_width * SCALE and current:
                    result.append(current)
                    current = word
                else:
                    current = trial
            result.append(current)
        return result

    def box(s, x, y, w, h, fill, line=None, radius=False):
        sh = s.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
            Inches(x),
            Inches(y),
            Inches(w),
            Inches(h),
        )
        sh.fill.solid()
        sh.fill.fore_color.rgb = rgb(fill)
        sh.line.fill.background() if not line else None
        if line:
            sh.line.color.rgb = rgb(line)
        sh.name = f"panel-{len(layout)}"
        draw.rectangle(
            [
                round(x * SCALE),
                round(y * SCALE),
                round((x + w) * SCALE),
                round((y + h) * SCALE),
            ],
            fill="#" + fill,
            outline="#" + line if line else None,
        )
        return sh

    def text(s, txt, x, y, w, h, size=22, color=INK, bold=False, mono=False, link=None):
        sh = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = sh.text_frame
        tf.word_wrap = True
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.TOP
        lines = wrap(txt, w, size, bold, mono)
        # Explicit wrapping aligns editable text with approximate preview layout.
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.font.name = "Consolas" if mono else "Segoe UI"
            p.font.size = Pt(size)
            p.font.bold = bold
            p.font.color.rgb = rgb(color)
            p.space_after = Pt(0)
            p.space_before = Pt(0)
            p.line_spacing = Pt(size * 1.2)
            if link and not isinstance(link, dict):
                for r in p.runs:
                    r.hyperlink.address = link
        if isinstance(link, dict):
            pending_links.append((sh, link["slide_id"]))
        required = len(lines) * size * 1.2 / 72
        if required > h + 0.02:
            overflow.append(
                {
                    "slide": len(prs.slides),
                    "text": txt,
                    "needed_inches": required,
                    "allocated_inches": h,
                }
            )
        for i, line in enumerate(lines):
            draw.text(
                (round(x * SCALE), round(y * SCALE + i * size * 1.2 * SCALE / 72)),
                line,
                font=font(size, bold, mono),
                fill="#" + color,
            )
        layout.append(
            {
                "slide": len(prs.slides),
                "text": txt,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "font_pt": size,
                "lines": len(lines),
            }
        )
        return sh

    def card(s, c, x, y, w, h):
        box(s, x, y, w, h, WHITE, LINE, True)
        box(s, x, y, 0.055, h, TEAL)
        title_size = 20 if h < 2.2 else 22
        title_h = (
            len(wrap(c["title"], w - 0.46, title_size, True)) * title_size * 1.2 / 72
        )
        text(
            s,
            c["title"],
            x + 0.23,
            y + 0.22,
            w - 0.46,
            title_h + 0.02,
            title_size,
            TEAL,
            True,
        )
        body_y = y + 0.22 + title_h + 0.12
        text(
            s,
            c["body"],
            x + 0.23,
            body_y,
            w - 0.46,
            y + h - body_y - 0.14,
            19 if h < 2.2 else 20,
        )

    def call(s, code, y=1.65):
        lines = code.count("\n") + 1
        h = 0.7 if lines == 1 else 1.05
        box(s, 0.65, y, 12.03, h, NAVY)
        text(s, code, 0.87, y + 0.14, 11.6, h - 0.22, 17, WHITE, mono=True)
        return y + h

    def table(s, t, x, y, width, row_h, cols=None, size=20):
        cols = cols or [1 / len(t["headers"])] * len(t["headers"])
        for ridx, row in enumerate([t["headers"]] + t["rows"]):
            xx = x
            for col, frac in zip(row, cols):
                ww = width * frac
                fill = NAVY if ridx == 0 else (WHITE if ridx % 2 else "EBF0F5")
                box(s, xx, y + ridx * row_h, ww, row_h, fill, LINE)
                text(
                    s,
                    col,
                    xx + 0.15,
                    y + ridx * row_h + 0.14,
                    ww - 0.3,
                    row_h - 0.19,
                    size,
                    WHITE if ridx == 0 else INK,
                    ridx == 0,
                )
                xx += ww
        return y + (len(t["rows"]) + 1) * row_h

    for index, d in enumerate(data["slides"], 1):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = rgb(BG)
        canvas = Image.new("RGB", (round(W * SCALE), round(H * SCALE)), "#" + BG)
        draw = ImageDraw.Draw(canvas)
        identifier = d.get("id", str(index))
        if identifier in slide_by_id:
            raise ValueError(f"Duplicate slide id: {identifier}")
        slide_by_id[identifier] = s
        cover = d["layout"] == "cover"
        box(s, 0, 0, W, 0.14, TEAL)
        text(s, d["section"].upper(), 0.65, 0.35, 11.8, 0.32, 12, TEAL, True)
        text(
            s,
            d["title"],
            0.65,
            0.87,
            12.02,
            1.4 if cover else 0.7,
            34 if cover else 29,
            NAVY,
            True,
        )
        kind = d["layout"]
        if cover:
            text(s, d["subtitle"], 0.65, 2.45, 12, 0.5, 20, TEAL, True)
            text(s, d["lead"], 0.65, 3.14, 11.8, 0.86, 25)
            for i, c in enumerate(d["cards"]):
                card(s, c, 0.65 + i * 6.15, 4.3, 5.88, 1.95)
        elif kind == "cards":
            text(s, d["lead"], 0.65, 1.7, 12, 0.8, 24)
            for i, c in enumerate(d["cards"]):
                card(s, c, 0.65 + i * 4.08, 2.8, 3.87, 3.25)
        elif kind == "tools":
            text(s, d["lead"], 0.65, 1.7, 12, 0.8, 24)
            for i, t in enumerate(d["tools"]):
                y = 2.73 + i * 1.17
                box(s, 0.65, y, 12.03, 1.05, WHITE, LINE)
                text(s, t["name"], 0.86, y + 0.15, 3.32, 0.37, 20, TEAL, True, True)
                text(s, t["input"], 4.22, y + 0.1, 8.1, 0.3, 13, MUTED, mono=True)
                text(s, t["output"], 4.22, y + 0.43, 8.1, 0.61, 18)
        elif kind in ["pairs", "next"]:
            for i, c in enumerate(d["pairs"]):
                card(s, c, 0.65 + (i % 2) * 6.15, 1.8 + (i // 2) * 2.25, 5.88, 2.1)
            if kind == "next":
                text(s, d["takeaway"], 0.65, 6.22, 12, 0.56, 17, TEAL, True)
        elif kind == "navigation":
            end = call(s, d["code"])
            text(s, d["lead"], 0.65, end + 0.25, 12, 0.48, 25, TEAL, True)
            end = table(s, d["table"], 0.65, 3.28, 12.03, 0.68, [0.31, 0.26, 0.43], 22)
            text(s, d["takeaway"], 0.65, end + 0.35, 12, 0.95, 23)
        elif kind == "dates":
            text(s, d["lead"], 0.65, 1.7, 12, 0.5, 24)
            end = table(s, d["table"], 0.65, 2.42, 12.03, 0.51, [0.44, 0.25, 0.31], 18)
            text(s, d["takeaway"], 0.65, end + 0.3, 12, 0.82, 22)
        elif kind == "catalog":
            end = call(s, d["code"])
            text(s, d["lead"], 0.65, end + 0.25, 12, 0.78, 22, TEAL, True)
            end = table(s, d["table"], 0.65, 3.75, 12.03, 0.61, [0.27, 0.42, 0.31], 20)
            text(s, d["takeaway"], 0.65, end + 0.27, 12, 0.88, 22)
        elif kind == "pdf":
            end = call(s, d["code"])
            for i, c in enumerate(d["cards"]):
                card(s, c, 0.65 + i * 6.15, end + 0.32, 5.88, 2.6)
            text(s, d["takeaway"], 0.65, 5.96, 12, 0.68, 20, TEAL, True)
        elif kind == "evaluation":
            for i, c in enumerate(d["cards"]):
                card(s, c, 0.65 + i * 6.15, 1.8, 5.88, 2.87)
            text(s, d["metrics"], 0.65, 4.95, 12, 0.76, 21, TEAL, True)
            text(s, d["takeaway"], 0.65, 5.75, 12, 0.86, 20)
        elif kind == "sources":
            for i, link in enumerate(d["links"]):
                text(
                    s,
                    link["label"],
                    0.75,
                    1.77 + i * 0.55,
                    11.7,
                    0.42,
                    21,
                    TEAL,
                    link=link["target"],
                )
            text(s, d["takeaway"], 0.65, 5.5, 12, 0.95, 22)
        elif kind == "media":
            media = d["media"]
            movie = Path(media["path"])
            if not movie.is_absolute():
                movie = SOURCE.parent / movie
            if not movie.is_file():
                raise FileNotFoundError(movie)
            aspect = media.get("aspect_ratio", 16 / 9)
            bounds = media.get("bounds", {})
            width = bounds.get("width", min(W - 1.3, (H - 2.7) * aspect))
            height = bounds.get("height", width / aspect)
            x = bounds.get("x", (W - width) / 2)
            y = bounds.get("y", 1.65)
            poster_path = media.get("poster_image")
            if poster_path is not None:
                poster = Path(poster_path)
                if not poster.is_absolute():
                    poster = SOURCE.parent / poster
                preview = Image.open(poster).convert("RGB")
                poster = str(poster)
            else:
                preview = Image.new(
                    "RGB", (round(width * SCALE), round(height * SCALE)), "#" + NAVY
                )
                poster_draw = ImageDraw.Draw(preview)
                center_x, center_y = preview.width / 2, preview.height / 2 - 35
                poster_draw.polygon(
                    [
                        (center_x - 35, center_y - 55),
                        (center_x - 35, center_y + 55),
                        (center_x + 60, center_y),
                    ],
                    fill="#" + CYAN,
                )
                caption = media.get("caption", "Play video")
                caption_lines = wrap(caption, width - 0.8, 22)
                for row, line in enumerate(caption_lines):
                    label_font = font(22)
                    label_x = (preview.width - label_font.getlength(line)) / 2
                    poster_draw.text(
                        (label_x, center_y + 90 + row * 44),
                        line,
                        font=label_font,
                        fill="#" + WHITE,
                    )
                poster = io.BytesIO()
                preview.save(poster, format="PNG")
                poster.seek(0)
            shape = s.shapes.add_movie(
                str(movie),
                Inches(x),
                Inches(y),
                Inches(width),
                Inches(height),
                poster_frame_image=poster,
                mime_type=media.get("mime_type")
                or mimetypes.guess_type(movie)[0]
                or "video/unknown",
            )
            shape.name = media.get("name", "Embedded video")
            canvas.paste(
                preview.resize((round(width * SCALE), round(height * SCALE))),
                (round(x * SCALE), round(y * SCALE)),
            )
            media_records.append(
                {
                    "slide_id": identifier,
                    "path": str(movie.resolve()),
                    "bytes": movie.stat().st_size,
                    "shape_id": shape.shape_id,
                }
            )
            layout.append(
                {
                    "slide": index,
                    "kind": "media",
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                }
            )
        else:
            raise ValueError(f"Unsupported layout: {kind}")
        box(s, 0.65, 6.88, 12.03, 0.008, LINE)
        text(s, d.get("scope", ""), 0.65, 6.99, 11.65, 0.36, 11, MUTED)
        text(s, f"{index:02d}", 12.3, 6.98, 0.38, 0.3, 12, TEAL, True)
        refs = [
            next(v for v in data.get("sources", []) if v["id"] == r)
            for r in d.get("source_refs", [])
        ]
        note = (
            "\n\n".join(d.get("notes", []))
            + "\n\nEvidence navigation:\n"
            + "\n".join(
                r["id"]
                + ": "
                + r["label"]
                + " | "
                + r.get("path", r.get("url", ""))
                + (" | " + r["observation_id"] if "observation_id" in r else "")
                for r in refs
            )
        )
        s.notes_slide.notes_text_frame.text = note
        if CACHE is not None:
            canvas.save(CACHE / f"slide-{index:02d}-approximate.png")
            render_pages.append(canvas)

    for shape, identifier in pending_links:
        shape.click_action.target_slide = slide_by_id[identifier]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUTPUT)
    if CACHE is not None and render_pages:
        thumbs = []
        for i, page in enumerate(render_pages, 1):
            thumb = page.resize((640, 360))
            sheet = Image.new("RGB", (656, 392), "#D8E1E9")
            sheet.paste(thumb, (8, 8))
            ImageDraw.Draw(sheet).text(
                (8, 370),
                f"{i:02d} · Approximate layout preview",
                font=font(7.2),
                fill="#15334E",
            )
            thumbs.append(sheet)
        contact = Image.new(
            "RGB", (656 * 3, 392 * math.ceil(len(thumbs) / 3)), "#D8E1E9"
        )
        for i, thumb in enumerate(thumbs):
            contact.paste(thumb, ((i % 3) * 656, (i // 3) * 392))
        contact.save(CACHE / "contact-sheet-approximate.png")
        (CACHE / "layout-check.json").write_text(
            json.dumps(
                {
                    "preview_scope": "Pillow approximation; native rendering separate",
                    "overflow": overflow,
                    "text_boxes": layout,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "output": str(OUTPUT),
        "source": str(SOURCE),
        "slides": len(prs.slides),
        "media": media_records,
        "overflow": overflow,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        help="Presentation JSON; local media paths resolve beside this file",
    )
    parser.add_argument(
        "--output", type=Path, help="PPTX destination; defaults beside JSON"
    )
    parser.add_argument(
        "--preview-dir", type=Path, help="Optional approximate PNG/layout outputs"
    )
    parser.add_argument(
        "--font-dir",
        type=Path,
        help="Optional font directory searched before system font lookup",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_presentation(
                args.source,
                args.output,
                preview_dir=args.preview_dir,
                font_dir=args.font_dir,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
