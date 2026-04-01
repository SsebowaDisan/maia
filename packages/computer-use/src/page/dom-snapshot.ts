// ---------------------------------------------------------------------------
// DOM Snapshot – extracts numbered interactive elements with coordinates
// ---------------------------------------------------------------------------

/** Minimal CDP client interface (send method that returns a promise). */
export interface CDPClient {
  send(method: string, params?: Record<string, unknown>): Promise<any>;
}

// ---- Public types ---------------------------------------------------------

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface InteractiveElement {
  index: number;
  tag: string;
  type?: string;
  text: string;
  placeholder?: string;
  href?: string;
  value?: string;
  checked?: boolean;
  disabled: boolean;
  visible: boolean;
  rect: Rect;
  center: Point;
}

export interface FormField {
  elementIndex: number;
  label: string;
  type: string;
  value: string;
  required: boolean;
  valid: boolean;
  error?: string;
}

export interface DOMSnapshot {
  url: string;
  title: string;
  viewport: { width: number; height: number };
  scrollY: number;
  elements: InteractiveElement[];
  formState: FormField[];
  pageText: string;
}

// ---- Implementation -------------------------------------------------------

const MAX_ELEMENTS = 150;
const MAX_TEXT_LEN = 80;
const MAX_PAGE_TEXT = 5000;

/**
 * JavaScript snippet evaluated inside the page via Runtime.evaluate.
 * It returns a JSON-serialisable object conforming to DOMSnapshot.
 */
const SNAPSHOT_JS = `
(function () {
  // ---- helpers -----------------------------------------------------------
  var SELECTORS = [
    'a', 'button', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="menuitem"]',
    '[tabindex]', '[onclick]', '[contenteditable]'
  ];
  var MAX_ELEMENTS = ${MAX_ELEMENTS};
  var MAX_TEXT    = ${MAX_TEXT_LEN};
  var MAX_PAGE   = ${MAX_PAGE_TEXT};

  function trim(s, max) {
    if (!s) return '';
    s = s.replace(/\\s+/g, ' ').trim();
    return s.length > max ? s.slice(0, max) : s;
  }

  function isVisible(el) {
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    var cs = getComputedStyle(el);
    if (cs.display === 'none') return false;
    if (cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) === 0) return false;
    return true;
  }

  function labelFor(el) {
    // Explicit <label for="id">
    if (el.id) {
      var lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lbl) return trim(lbl.innerText || lbl.textContent, MAX_TEXT);
    }
    // Closest ancestor label
    var ancestor = el.closest('label');
    if (ancestor) return trim(ancestor.innerText || ancestor.textContent, MAX_TEXT);
    // aria-label
    if (el.getAttribute('aria-label')) return trim(el.getAttribute('aria-label'), MAX_TEXT);
    return '';
  }

  // ---- collect interactive elements --------------------------------------
  var seen = new Set();
  var collected = [];

  for (var s = 0; s < SELECTORS.length && collected.length < MAX_ELEMENTS; s++) {
    var nodes = document.querySelectorAll(SELECTORS[s]);
    for (var i = 0; i < nodes.length && collected.length < MAX_ELEMENTS; i++) {
      var el = nodes[i];
      if (seen.has(el)) continue;
      seen.add(el);

      var vis = isVisible(el);
      if (!vis) continue;

      var r = el.getBoundingClientRect();
      var rect = { x: r.x, y: r.y, width: r.width, height: r.height };
      var center = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      var entry = {
        index: collected.length,
        tag: el.tagName.toLowerCase(),
        text: trim(el.innerText || el.textContent, MAX_TEXT),
        disabled: !!el.disabled,
        visible: true,
        rect: rect,
        center: center
      };

      if (el.type) entry.type = el.type;
      if (el.placeholder) entry.placeholder = el.placeholder;
      if (el.href) entry.href = el.href;
      if (el.value !== undefined && el.value !== '') entry.value = String(el.value);
      if (el.checked !== undefined) entry.checked = !!el.checked;

      collected.push(entry);
    }
  }

  // ---- collect form fields -----------------------------------------------
  var formFields = [];
  var formEls = document.querySelectorAll('input, select, textarea');
  for (var f = 0; f < formEls.length; f++) {
    var fe = formEls[f];
    // Find matching element index
    var idx = -1;
    for (var c = 0; c < collected.length; c++) {
      // Compare by bounding rect as a stable identity
      var cr = collected[c].rect;
      var fr = fe.getBoundingClientRect();
      if (Math.abs(cr.x - fr.x) < 1 && Math.abs(cr.y - fr.y) < 1 &&
          Math.abs(cr.width - fr.width) < 1 && Math.abs(cr.height - fr.height) < 1) {
        idx = c;
        break;
      }
    }
    if (idx === -1) continue;

    var field = {
      elementIndex: idx,
      label: labelFor(fe),
      type: fe.type || fe.tagName.toLowerCase(),
      value: fe.value || '',
      required: !!fe.required,
      valid: typeof fe.checkValidity === 'function' ? fe.checkValidity() : true
    };

    if (!field.valid && fe.validationMessage) {
      field.error = fe.validationMessage;
    }

    formFields.push(field);
  }

  // ---- build snapshot ----------------------------------------------------
  var bodyText = (document.body.innerText || '').slice(0, MAX_PAGE);

  return {
    url: location.href,
    title: document.title,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    scrollY: window.scrollY,
    elements: collected,
    formState: formFields,
    pageText: bodyText
  };
})()
`;

/**
 * Capture a full DOM snapshot of the current page via CDP.
 */
export async function captureDOMSnapshot(client: CDPClient): Promise<DOMSnapshot> {
  const result = await client.send('Runtime.evaluate', {
    expression: SNAPSHOT_JS,
    returnByValue: true,
    awaitPromise: false,
  });

  if (result.exceptionDetails) {
    const msg =
      result.exceptionDetails.exception?.description ||
      result.exceptionDetails.text ||
      'Unknown error capturing DOM snapshot';
    throw new Error(`DOM snapshot failed: ${msg}`);
  }

  const snapshot: DOMSnapshot = result.result.value;

  if (!snapshot || !Array.isArray(snapshot.elements)) {
    throw new Error('DOM snapshot returned invalid data');
  }

  return snapshot;
}
