"""Browser-backed PDF renderer for slide decks."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image

from app.core.config import PROJECT_ROOT


logger = logging.getLogger(__name__)

SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900
DEFAULT_RENDERER_DIR = Path("/app/slide-renderer")


def render_deck_pdf_with_browser(
    deck: dict[str, Any],
    pdf_path: Path,
    *,
    timeout_seconds: int,
    screenshot_scale: float,
) -> None:
    """Render deck JSON through the static React slide renderer and save a raster PDF."""
    html_path = _find_renderer_html()
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    if not slides:
        raise ValueError("Slide deck has no slides to render.")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - exercised through fallback tests
        raise RuntimeError("Playwright is not installed for browser PDF rendering.") from exc

    timeout_ms = max(1, int(timeout_seconds)) * 1000
    scale = max(1, float(screenshot_scale))
    images: list[Image.Image] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--allow-file-access-from-files", "--disable-dev-shm-usage", "--no-sandbox"]
        )
        try:
            context = browser.new_context(
                viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
                device_scale_factor=scale,
            )
            context.route("**/*", lambda route: _route_static_renderer_request(route, html_path.parent))
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function("typeof window.renderSlideDeck === 'function'", timeout=timeout_ms)
            page.evaluate("deck => window.renderSlideDeck(deck)", deck)
            page.wait_for_function("window.__SLIDE_RENDER_READY__ === true", timeout=timeout_ms)
            page_count = page.locator(".slide-render-page").count()
            if page_count != len(slides):
                raise ValueError(f"Browser renderer produced {page_count} pages for {len(slides)} slides.")
            for index in range(page_count):
                screenshot = page.locator(".slide-render-page").nth(index).screenshot(
                    type="png",
                    animations="disabled",
                    timeout=timeout_ms,
                )
                images.append(Image.open(io.BytesIO(screenshot)).convert("RGB"))
        finally:
            browser.close()

    first_image, *rest = images
    first_image.save(pdf_path, "PDF", resolution=288, save_all=True, append_images=rest)


def _find_renderer_html() -> Path:
    candidates = [
        DEFAULT_RENDERER_DIR / "slide-renderer.html",
        PROJECT_ROOT / "frontend" / "dist" / "slide-renderer.html",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Slide renderer bundle was not found. Run `npm run build` in frontend or copy dist to /app/slide-renderer."
    )


def _route_static_renderer_request(route: Any, renderer_dir: Path) -> None:
    url = route.request.url
    if url.startswith(("data:", "blob:", "about:")):
        route.continue_()
        return

    parsed = urlparse(url)
    if parsed.scheme == "file":
        requested_path = Path(unquote(parsed.path)).resolve()
        try:
            requested_path.relative_to(renderer_dir.resolve())
        except ValueError:
            logger.warning("Blocked slide renderer file request outside bundle: %s", url)
            route.abort()
        else:
            route.continue_()
        return

    logger.warning("Blocked external slide renderer request: %s", url)
    route.abort()
