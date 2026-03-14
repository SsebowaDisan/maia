"""DOM snapshot — extracts a numbered, text-serialized index of all visible
interactive elements on the current page via Playwright's page.evaluate().

Inspired by page-agent's flatTreeToString() technique, implemented entirely
in Python with no JavaScript library dependency.

The snapshot is appended to every vision-model message alongside the
screenshot.  It helps the model target clicks precisely without having to
guess pixel coordinates purely from the image — the model can read
"[12] <button> 'Submit' @ (640, 420)" and click (640, 420) with confidence.

Output format:
    --- Page Context ---
    URL: https://example.com/form
    Title: Contact Us
    Viewport: 1280x800  ScrollY: 142

    Interactive elements:
    [0]  <a href="/home"> "Home" @ (64, 30)
    [1]  <input type="text"> "First name" @ (320, 210)
    [2]  <input type="email"> "Email address" @ (320, 260)
    [3]  <button> "Submit" @ (640, 420)
    ...
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum number of elements to include — keeps prompt tokens bounded.
_MAX_ELEMENTS = 150

# The JavaScript executed inside the page via page.evaluate().
# Returns the full snapshot string or null on failure.
_JS_SNAPSHOT = """
() => {
  try {
    const INTERACTIVE_TAGS = new Set([
      'A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA',
      'DETAILS', 'SUMMARY', 'LABEL',
    ]);
    const INTERACTIVE_ROLES = new Set([
      'button', 'link', 'checkbox', 'radio', 'combobox',
      'listbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
      'option', 'slider', 'spinbutton', 'switch', 'tab', 'textbox',
      'searchbox', 'treeitem',
    ]);

    function isVisible(el) {
      try {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none') return false;
        if (style.visibility === 'hidden') return false;
        if (parseFloat(style.opacity || '1') < 0.05) return false;
        if (rect.bottom < 0 || rect.top > window.innerHeight) return false;
        if (rect.right < 0 || rect.left > window.innerWidth) return false;
        return true;
      } catch { return false; }
    }

    function getLabel(el) {
      const candidates = [
        el.getAttribute('aria-label'),
        el.getAttribute('placeholder'),
        el.getAttribute('title'),
        el.getAttribute('alt'),
        el.getAttribute('value'),
        (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
        el.getAttribute('name'),
      ];
      for (const c of candidates) {
        if (c && c.trim()) return c.trim().slice(0, 80);
      }
      return '';
    }

    const seen = new WeakSet();
    const results = [];
    let index = 0;

    const MAX = """ + str(_MAX_ELEMENTS) + """;

    // Use TreeWalker for efficient DOM traversal
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_ELEMENT,
      null,
    );

    let node;
    while ((node = walker.nextNode()) && index < MAX) {
      const el = node;
      if (seen.has(el)) continue;
      seen.add(el);

      const tag = el.tagName;
      const role = (el.getAttribute('role') || '').toLowerCase();
      const tabIndex = el.getAttribute('tabindex');

      const isInteractive = (
        INTERACTIVE_TAGS.has(tag) ||
        INTERACTIVE_ROLES.has(role) ||
        el.hasAttribute('onclick') ||
        el.hasAttribute('onkeydown') ||
        (tabIndex !== null && tabIndex !== '-1')
      );

      if (!isInteractive) continue;
      if (!isVisible(el)) continue;

      const rect = el.getBoundingClientRect();
      const cx = Math.round(rect.left + rect.width / 2);
      const cy = Math.round(rect.top + rect.height / 2);
      const label = getLabel(el);
      const tagLow = tag.toLowerCase();

      // Build compact descriptor
      let desc = '[' + index + '] <' + tagLow;
      const elType = el.getAttribute('type');
      if (elType) desc += ' type="' + elType + '"';
      const href = el.getAttribute('href');
      if (href) {
        const hrefShort = href.length > 60 ? href.slice(0, 57) + '...' : href;
        desc += ' href="' + hrefShort + '"';
      }
      if (role && !INTERACTIVE_TAGS.has(tag)) desc += ' role="' + role + '"';
      desc += '>';
      if (label) desc += ' "' + label + '"';
      desc += ' @ (' + cx + ',' + cy + ')';

      results.push(desc);
      index++;
    }

    const scrollY = Math.round(window.scrollY);
    const pageInfo = [
      'URL: ' + location.href,
      'Title: ' + document.title,
      'Viewport: ' + window.innerWidth + 'x' + window.innerHeight +
        (scrollY > 0 ? '  ScrollY: ' + scrollY : ''),
    ].join('\\n');

    return pageInfo + '\\n\\nInteractive elements:\\n' + results.join('\\n');
  } catch (err) {
    return null;
  }
}
"""


def get_dom_snapshot(page: Any) -> str | None:
    """Run the DOM indexer inside *page* and return the snapshot string.

    Args:
        page: A Playwright ``Page`` object (sync API).

    Returns:
        A multi-line string listing page context and numbered elements,
        or ``None`` if the page is not ready or evaluation fails.
    """
    try:
        result = page.evaluate(_JS_SNAPSHOT)
        if not result or not isinstance(result, str):
            return None
        return result
    except Exception as exc:
        logger.debug("DOM snapshot failed: %s", exc)
        return None


def format_snapshot_block(snapshot: str | None) -> str:
    """Wrap the snapshot in a clearly delimited text block for the LLM."""
    if not snapshot:
        return ""
    return (
        "\n--- Page Context (DOM index) ---\n"
        + snapshot.strip()
        + "\n--- End DOM index ---\n"
        "\nUse the element coordinates above when choosing where to click. "
        "Coordinates are absolute pixel positions within the viewport."
    )
