// ---------------------------------------------------------------------------
// Element Resolver – maps an ElementTarget to page coordinates
// ---------------------------------------------------------------------------

import type {
  CDPClient,
  DOMSnapshot,
  InteractiveElement,
  Point,
  Rect,
} from './dom-snapshot';

// ---- Public types ---------------------------------------------------------

export type ElementTarget =
  | { elementId: number }
  | { text: string }
  | { selector: string }
  | { label: string }
  | { role: string; name?: string }
  | { near: string }
  | { coordinates: { x: number; y: number } };

export type ResolutionStrategy =
  | 'elementId'
  | 'text'
  | 'selector'
  | 'label'
  | 'role'
  | 'near'
  | 'coordinates';

export interface ResolvedElement {
  center: Point;
  rect: Rect;
  tag: string;
  text: string;
  elementIndex: number | null;
  strategy: ResolutionStrategy;
  confidence: number;
}

// ---- Helpers --------------------------------------------------------------

function distance(a: Point, b: Point): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

function fuzzyMatch(haystack: string, needle: string): number {
  const h = haystack.toLowerCase();
  const n = needle.toLowerCase();
  if (h === n) return 1.0;
  if (h.includes(n)) return 0.9;
  // Simple token overlap
  const needleTokens = n.split(/\s+/);
  const matched = needleTokens.filter((t) => h.includes(t)).length;
  return matched / needleTokens.length * 0.8;
}

function elementToResolved(
  el: InteractiveElement,
  strategy: ResolutionStrategy,
  confidence: number,
): ResolvedElement {
  return {
    center: el.center,
    rect: el.rect,
    tag: el.tag,
    text: el.text,
    elementIndex: el.index,
    strategy,
    confidence,
  };
}

// ---- Strategy implementations ---------------------------------------------

function byElementId(
  target: { elementId: number },
  snapshot: DOMSnapshot,
): ResolvedElement | null {
  const el = snapshot.elements.find((e) => e.index === target.elementId);
  if (!el) return null;
  return elementToResolved(el, 'elementId', 1.0);
}

function byText(
  target: { text: string },
  snapshot: DOMSnapshot,
): ResolvedElement | null {
  let best: InteractiveElement | null = null;
  let bestScore = 0;

  for (const el of snapshot.elements) {
    const score = fuzzyMatch(el.text, target.text);
    if (score > bestScore) {
      bestScore = score;
      best = el;
    }
    // Also check placeholder, value, href
    for (const field of [el.placeholder, el.value, el.href]) {
      if (field) {
        const s = fuzzyMatch(field, target.text);
        if (s > bestScore) {
          bestScore = s;
          best = el;
        }
      }
    }
  }

  if (!best || bestScore < 0.3) return null;
  return elementToResolved(best, 'text', bestScore);
}

async function bySelector(
  target: { selector: string },
  client: CDPClient,
): Promise<ResolvedElement | null> {
  const js = `
    (function() {
      var el = document.querySelector(${JSON.stringify(target.selector)});
      if (!el) return null;
      var r = el.getBoundingClientRect();
      return {
        tag: el.tagName.toLowerCase(),
        text: (el.innerText || el.textContent || '').trim().slice(0, 80),
        rect: { x: r.x, y: r.y, width: r.width, height: r.height },
        center: { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }
      };
    })()
  `;

  const result = await client.send('Runtime.evaluate', {
    expression: js,
    returnByValue: true,
  });

  if (result.exceptionDetails || !result.result.value) return null;

  const v = result.result.value;
  return {
    center: v.center,
    rect: v.rect,
    tag: v.tag,
    text: v.text,
    elementIndex: null,
    strategy: 'selector',
    confidence: 1.0,
  };
}

function byLabel(
  target: { label: string },
  snapshot: DOMSnapshot,
): ResolvedElement | null {
  let best: { field: typeof snapshot.formState[0]; score: number } | null = null;

  for (const field of snapshot.formState) {
    const score = fuzzyMatch(field.label, target.label);
    if (score > (best?.score ?? 0)) {
      best = { field, score };
    }
  }

  if (!best || best.score < 0.3) return null;
  const el = snapshot.elements.find((e) => e.index === best!.field.elementIndex);
  if (!el) return null;
  return elementToResolved(el, 'label', best.score);
}

function byRole(
  target: { role: string; name?: string },
  snapshot: DOMSnapshot,
): ResolvedElement | null {
  const roleTagMap: Record<string, string[]> = {
    button: ['button'],
    link: ['a'],
    menuitem: [],
    textbox: ['input', 'textarea'],
    checkbox: ['input'],
    radio: ['input'],
    combobox: ['select'],
  };

  const matchTags = roleTagMap[target.role] || [];

  const candidates = snapshot.elements.filter((el) => {
    // Check explicit ARIA role via type field or tag
    if (el.tag === target.role) return true;
    if (matchTags.includes(el.tag)) {
      // For input, check type alignment
      if (el.tag === 'input') {
        if (target.role === 'checkbox' && el.type === 'checkbox') return true;
        if (target.role === 'radio' && el.type === 'radio') return true;
        if (target.role === 'textbox' && (!el.type || el.type === 'text' || el.type === 'email' || el.type === 'search' || el.type === 'url' || el.type === 'tel' || el.type === 'password')) return true;
        return false;
      }
      return true;
    }
    return false;
  });

  if (candidates.length === 0) return null;

  if (target.name) {
    let best: InteractiveElement | null = null;
    let bestScore = 0;
    for (const el of candidates) {
      const score = fuzzyMatch(el.text, target.name);
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    }
    if (best && bestScore >= 0.3) {
      return elementToResolved(best, 'role', bestScore);
    }
  }

  return elementToResolved(candidates[0], 'role', 0.7);
}

function byNear(
  target: { near: string },
  snapshot: DOMSnapshot,
): ResolvedElement | null {
  // First find the anchor element by text
  const anchor = byText({ text: target.near }, snapshot);
  if (!anchor) return null;

  let closest: InteractiveElement | null = null;
  let closestDist = Infinity;

  for (const el of snapshot.elements) {
    if (el.index === anchor.elementIndex) continue;
    const d = distance(el.center, anchor.center);
    if (d < closestDist) {
      closestDist = d;
      closest = el;
    }
  }

  if (!closest) return null;
  // Confidence decreases with distance
  const confidence = Math.max(0.3, 1.0 - closestDist / 1000);
  return elementToResolved(closest, 'near', confidence);
}

function byCoordinates(target: {
  coordinates: { x: number; y: number };
}): ResolvedElement {
  return {
    center: { x: target.coordinates.x, y: target.coordinates.y },
    rect: { x: target.coordinates.x, y: target.coordinates.y, width: 0, height: 0 },
    tag: 'unknown',
    text: '',
    elementIndex: null,
    strategy: 'coordinates',
    confidence: 1.0,
  };
}

// ---- Public API -----------------------------------------------------------

/**
 * Resolve an ElementTarget to a ResolvedElement using a cascade of strategies.
 */
export async function resolve(
  target: ElementTarget,
  snapshot: DOMSnapshot,
  client: CDPClient,
): Promise<ResolvedElement> {
  // 1. elementId
  if ('elementId' in target) {
    const r = byElementId(target, snapshot);
    if (r) return r;
    throw new Error(`Element with id [${target.elementId}] not found in snapshot`);
  }

  // 2. text
  if ('text' in target) {
    const r = byText(target, snapshot);
    if (r) return r;
    throw new Error(`No element matching text "${target.text}" found`);
  }

  // 3. selector
  if ('selector' in target) {
    const r = await bySelector(target, client);
    if (r) return r;
    throw new Error(`No element matching selector "${target.selector}" found`);
  }

  // 4. label
  if ('label' in target) {
    const r = byLabel(target, snapshot);
    if (r) return r;
    throw new Error(`No form field with label "${target.label}" found`);
  }

  // 5. role
  if ('role' in target) {
    const r = byRole(target, snapshot);
    if (r) return r;
    throw new Error(`No element with role "${target.role}" found`);
  }

  // 6. near
  if ('near' in target) {
    const r = byNear(target, snapshot);
    if (r) return r;
    throw new Error(`No element found near "${target.near}"`);
  }

  // 7. coordinates
  if ('coordinates' in target) {
    return byCoordinates(target);
  }

  throw new Error('Invalid ElementTarget: no recognized target key');
}
