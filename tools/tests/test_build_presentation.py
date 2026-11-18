# /// script
# dependencies = ["python-pptx", "Pillow"]
# ///
"""Exercise JSON callers with ordinary slides, media, and internal navigation."""

import importlib.util
import json
import os
import posixpath
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/build_presentation.py"
SPEC = importlib.util.spec_from_file_location("presentation_builder", MODULE_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
ASSET = ROOT / "docs/irs-public-mcp-recorded-workflow.mp4"
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class PresentationBuilderTests(unittest.TestCase):
    def setUp(self):
        base = Path(
            os.environ.get("PRESENTATION_TEST_TMP", ROOT / ".cache/presentation-tests")
        ).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.folder = (base / f"case-{uuid.uuid4().hex}").resolve()
        self.assertTrue(self.folder.is_relative_to(base))
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder)

    def build(self, slides):
        source = self.folder / "caller.json"
        output = self.folder / "caller.pptx"
        data = {
            "purpose": "Caller-selected demonstration",
            "author": "Caller team",
            "sources": [],
            "slides": slides,
        }
        source.write_text(json.dumps(data), encoding="utf-8")
        report = BUILDER.build_presentation(source, output)
        self.assertEqual(data, json.loads(source.read_text(encoding="utf-8")))
        self.assertEqual(report["slides"], len(slides))
        return output, report

    def test_ordinary_layouts_keep_text_and_external_navigation(self):
        slides = [
            {
                "id": "overview",
                "layout": "cards",
                "section": "Overview",
                "title": "Caller overview",
                "lead": "Source text remains editable",
                "cards": [{"title": "Choice", "body": "Useful caller content"}],
            },
            {
                "id": "references",
                "layout": "sources",
                "section": "Navigation",
                "title": "Caller references",
                "links": [
                    {"label": "Reference", "target": "https://example.test/reference"}
                ],
                "takeaway": "Follow selected source",
            },
        ]
        output, report = self.build(slides)
        self.assertEqual(report["media"], [])
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertFalse(any(name.endswith(".mp4") for name in archive.namelist()))
            visible = [
                text.text
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                for text in ET.fromstring(archive.read(name)).findall(".//a:t", NS)
            ]
            self.assertIn("Caller overview", visible)
            self.assertIn("Useful caller content", visible)
            self.assertIn("Caller references", visible)
            relationships = ET.fromstring(
                archive.read("ppt/slides/_rels/slide2.xml.rels")
            )
            self.assertTrue(
                any(
                    item.attrib.get("Target") == "https://example.test/reference"
                    and item.attrib.get("TargetMode") == "External"
                    for item in relationships
                )
            )

    def test_media_resolves_relative_source_and_internal_slide_target(self):
        slides = [
            {
                "id": "jump",
                "layout": "sources",
                "section": "Navigation",
                "title": "Watch selected example",
                "links": [{"label": "Play", "target": {"slide_id": "watch-changes"}}],
                "takeaway": "Embedded playback follows",
            },
            {
                "id": "watch-changes",
                "layout": "media",
                "section": "Example",
                "title": "Caller-selected recording",
                "media": {
                    "path": os.path.relpath(ASSET, self.folder),
                    "mime_type": "video/mp4",
                    "caption": "Play example",
                },
            },
        ]
        output, report = self.build(slides)
        self.assertEqual(report["media"][0]["path"], str(ASSET.resolve()))
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            video = next(name for name in archive.namelist() if name.endswith(".mp4"))
            self.assertEqual(archive.read(video), ASSET.read_bytes())
            media_relationships = ET.fromstring(
                archive.read("ppt/slides/_rels/slide2.xml.rels")
            )
            self.assertTrue(
                any(
                    posixpath.normpath(
                        posixpath.join("ppt/slides", item.attrib["Target"])
                    )
                    == video
                    and item.attrib.get("TargetMode") != "External"
                    for item in media_relationships
                )
            )
            media_slide = ET.fromstring(archive.read("ppt/slides/slide2.xml"))
            self.assertIsNotNone(media_slide.find(".//p:video", NS))
            jump = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
            click = next(
                item
                for item in jump.findall(".//a:hlinkClick", NS)
                if item.attrib.get("action") == "ppaction://hlinksldjump"
            )
            rels = {
                item.attrib["Id"]: item
                for item in ET.fromstring(
                    archive.read("ppt/slides/_rels/slide1.xml.rels")
                )
            }
            target = rels[click.attrib[f"{{{NS['r']}}}id"]]
            self.assertEqual(target.attrib["Target"], "slide2.xml")
            self.assertNotEqual(target.attrib.get("TargetMode"), "External")

    def test_media_uses_supplied_poster_path(self):
        images = self.folder / "images"
        images.mkdir()
        poster = images / "preview with spaces.png"
        Image.new("RGB", (320, 180), "#203040").save(poster)
        output, report = self.build(
            [
                {
                    "id": "poster-example",
                    "layout": "media",
                    "section": "Example",
                    "title": "Caller-supplied poster",
                    "media": {
                        "path": os.path.relpath(ASSET, self.folder),
                        "mime_type": "video/mp4",
                        "poster_image": "images/preview with spaces.png",
                    },
                }
            ]
        )
        self.assertEqual(report["media"][0]["path"], str(ASSET.resolve()))
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            embedded_images = [
                archive.read(name)
                for name in archive.namelist()
                if name.startswith("ppt/media/") and name.endswith(".png")
            ]
            self.assertIn(poster.read_bytes(), embedded_images)
            video = next(name for name in archive.namelist() if name.endswith(".mp4"))
            self.assertEqual(archive.read(video), ASSET.read_bytes())

    def test_missing_media_preserves_existing_destination(self):
        source = self.folder / "input.json"
        destination = self.folder / "existing.pptx"
        previous = b"Caller-owned previous output"
        destination.write_bytes(previous)
        source.write_text(
            json.dumps(
                {
                    "slides": [
                        {
                            "layout": "media",
                            "section": "Example",
                            "title": "Unavailable asset",
                            "media": {"path": "missing.mp4"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(FileNotFoundError):
            BUILDER.build_presentation(source, destination)
        self.assertEqual(destination.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
