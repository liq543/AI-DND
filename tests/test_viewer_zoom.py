"""The live table zooms by redrawing the map SVG at its on-screen size, never by CSS-scaling a layer,
and pans by moving that layer alone.

A CSS scale() on a composited layer stretches a bitmap painted at another size, so lines, text and
art go soft when the player zooms. A stretch is allowed only for a moment mid-gesture, always
followed by a sharp redraw. These checks keep a lasting blur from coming back.
"""
import re
import unittest
from pathlib import Path

VIEWER = Path(__file__).resolve().parent.parent / "viewer"


class ViewerZoomStaysSharp(unittest.TestCase):
    def test_mapwrap_is_never_scaled(self):
        css = (VIEWER / "style.css").read_text(encoding="utf-8")
        rule = re.search(r"#mapwrap\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertNotIn("scale", rule.group(1))

    def test_panning_does_not_relayout_the_svg(self):
        js = (VIEWER / "app.js").read_text(encoding="utf-8")
        self.assertIn("drawn.s !== z.s", js)
        self.assertIn("requestAnimationFrame(() => { zoomFrame = 0;", js)

    def test_zoom_resizes_the_svg_instead_of_scaling(self):
        js = (VIEWER / "app.js").read_text(encoding="utf-8")
        self.assertIn('svg.setAttribute("width", W * z.s)', js)
        # any stretch is only a stopgap mid-gesture: a settle redraw always follows it
        self.assertIn("settleTimer = setTimeout(", js)


if __name__ == "__main__":
    unittest.main()
