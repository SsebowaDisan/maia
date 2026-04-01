// ---------------------------------------------------------------------------
// Input Controller – mouse + keyboard actions via CDP
// ---------------------------------------------------------------------------

import type { CDPClient, DOMSnapshot } from '../page/dom-snapshot';
import type { ElementTarget, ResolvedElement } from '../page/element-resolver';
import { resolve } from '../page/element-resolver';

// ---- Public types ---------------------------------------------------------

export interface ActionResult {
  success: boolean;
  strategy: string;
  element: ResolvedElement | null;
  changed: boolean;
  timeMs: number;
  retries: number;
  error?: string;
}

export interface ClickOptions {
  /** Double-click instead of single */
  double?: boolean;
  /** Right-click */
  right?: boolean;
  /** Click count override */
  clickCount?: number;
}

export interface TypeOptions {
  /** Clear existing content before typing */
  clear?: boolean;
  /** Use insertText for speed (less realistic) */
  fast?: boolean;
  /** Delay between keystrokes in ms */
  delay?: number;
}

export interface PressOptions {
  /** Hold Shift */
  shift?: boolean;
  /** Hold Ctrl / Meta */
  ctrl?: boolean;
  /** Hold Alt */
  alt?: boolean;
  /** Hold Meta (Cmd on Mac) */
  meta?: boolean;
}

// ---- Key mappings ---------------------------------------------------------

interface KeyDef {
  key: string;
  code: string;
  keyCode: number;
  text?: string;
}

const KEY_MAP: Record<string, KeyDef> = {
  Enter:      { key: 'Enter',      code: 'Enter',      keyCode: 13, text: '\r' },
  Tab:        { key: 'Tab',        code: 'Tab',        keyCode: 9 },
  Escape:     { key: 'Escape',     code: 'Escape',     keyCode: 27 },
  Backspace:  { key: 'Backspace',  code: 'Backspace',  keyCode: 8 },
  Delete:     { key: 'Delete',     code: 'Delete',     keyCode: 46 },
  ArrowUp:    { key: 'ArrowUp',    code: 'ArrowUp',    keyCode: 38 },
  ArrowDown:  { key: 'ArrowDown',  code: 'ArrowDown',  keyCode: 40 },
  ArrowLeft:  { key: 'ArrowLeft',  code: 'ArrowLeft',  keyCode: 37 },
  ArrowRight: { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
  Home:       { key: 'Home',       code: 'Home',       keyCode: 36 },
  End:        { key: 'End',        code: 'End',        keyCode: 35 },
  PageUp:     { key: 'PageUp',     code: 'PageUp',     keyCode: 33 },
  PageDown:   { key: 'PageDown',   code: 'PageDown',   keyCode: 34 },
  Space:      { key: ' ',          code: 'Space',      keyCode: 32, text: ' ' },
  // Modifier keys (used for press with modifiers)
  Shift:      { key: 'Shift',      code: 'ShiftLeft',  keyCode: 16 },
  Control:    { key: 'Control',    code: 'ControlLeft', keyCode: 17 },
  Alt:        { key: 'Alt',        code: 'AltLeft',    keyCode: 18 },
  Meta:       { key: 'Meta',       code: 'MetaLeft',   keyCode: 91 },
};

// ---- Utilities ------------------------------------------------------------

function modifiers(opts?: PressOptions): number {
  let m = 0;
  if (opts?.alt) m |= 1;
  if (opts?.ctrl) m |= 2;
  if (opts?.meta) m |= 4;
  if (opts?.shift) m |= 8;
  return m;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function ok(
  element: ResolvedElement | null,
  strategy: string,
  changed: boolean,
  start: number,
): ActionResult {
  return {
    success: true,
    strategy,
    element,
    changed,
    timeMs: Date.now() - start,
    retries: 0,
  };
}

function fail(
  error: string,
  element: ResolvedElement | null,
  strategy: string,
  start: number,
): ActionResult {
  return {
    success: false,
    strategy,
    element,
    changed: false,
    timeMs: Date.now() - start,
    retries: 0,
    error,
  };
}

// ---- InputController class ------------------------------------------------

export class InputController {
  private client: CDPClient;

  constructor(client: CDPClient) {
    this.client = client;
  }

  // ---- Mouse helpers ------------------------------------------------------

  private async moveMouse(x: number, y: number): Promise<void> {
    await this.client.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved',
      x,
      y,
    });
  }

  private async mouseDown(
    x: number,
    y: number,
    button: 'left' | 'right' = 'left',
    clickCount = 1,
  ): Promise<void> {
    await this.client.send('Input.dispatchMouseEvent', {
      type: 'mousePressed',
      x,
      y,
      button,
      clickCount,
      buttons: button === 'left' ? 1 : 2,
    });
  }

  private async mouseUp(
    x: number,
    y: number,
    button: 'left' | 'right' = 'left',
    clickCount = 1,
  ): Promise<void> {
    await this.client.send('Input.dispatchMouseEvent', {
      type: 'mouseReleased',
      x,
      y,
      button,
      clickCount,
    });
  }

  // ---- Key helpers --------------------------------------------------------

  private async keyDown(
    keyDef: KeyDef,
    mods = 0,
  ): Promise<void> {
    await this.client.send('Input.dispatchKeyEvent', {
      type: keyDef.text ? 'keyDown' : 'rawKeyDown',
      key: keyDef.key,
      code: keyDef.code,
      windowsVirtualKeyCode: keyDef.keyCode,
      nativeVirtualKeyCode: keyDef.keyCode,
      modifiers: mods,
      text: keyDef.text || '',
      unmodifiedText: keyDef.text || '',
    });
  }

  private async keyChar(char: string): Promise<void> {
    await this.client.send('Input.dispatchKeyEvent', {
      type: 'char',
      text: char,
      unmodifiedText: char,
      key: char,
    });
  }

  private async keyUp(
    keyDef: KeyDef,
    mods = 0,
  ): Promise<void> {
    await this.client.send('Input.dispatchKeyEvent', {
      type: 'keyUp',
      key: keyDef.key,
      code: keyDef.code,
      windowsVirtualKeyCode: keyDef.keyCode,
      nativeVirtualKeyCode: keyDef.keyCode,
      modifiers: mods,
    });
  }

  // ---- Resolve helper -----------------------------------------------------

  private async resolveTarget(
    target: ElementTarget,
    snapshot: DOMSnapshot,
  ): Promise<ResolvedElement> {
    return resolve(target, snapshot, this.client);
  }

  // ---- Public actions -----------------------------------------------------

  /**
   * Click an element.
   */
  async click(
    target: ElementTarget,
    snapshot: DOMSnapshot,
    opts?: ClickOptions,
  ): Promise<ActionResult> {
    const start = Date.now();
    let el: ResolvedElement;
    try {
      el = await this.resolveTarget(target, snapshot);
    } catch (err: any) {
      return fail(err.message, null, 'unknown', start);
    }

    const { x, y } = el.center;
    const button: 'left' | 'right' = opts?.right ? 'right' : 'left';
    const clickCount = opts?.clickCount ?? (opts?.double ? 2 : 1);

    try {
      await this.moveMouse(x, y);
      await this.mouseDown(x, y, button, 1);
      await this.mouseUp(x, y, button, 1);

      if (clickCount === 2) {
        await this.mouseDown(x, y, button, 2);
        await this.mouseUp(x, y, button, 2);
      }

      return ok(el, el.strategy, true, start);
    } catch (err: any) {
      return fail(err.message, el, el.strategy, start);
    }
  }

  /**
   * Type text into an element (clicks to focus first).
   */
  async type(
    target: ElementTarget,
    text: string,
    snapshot: DOMSnapshot,
    opts?: TypeOptions,
  ): Promise<ActionResult> {
    const start = Date.now();
    let el: ResolvedElement;
    try {
      el = await this.resolveTarget(target, snapshot);
    } catch (err: any) {
      return fail(err.message, null, 'unknown', start);
    }

    try {
      // Click to focus
      const { x, y } = el.center;
      await this.moveMouse(x, y);
      await this.mouseDown(x, y, 'left', 1);
      await this.mouseUp(x, y, 'left', 1);

      // Clear existing content if requested
      if (opts?.clear) {
        // Ctrl+A to select all
        await this.keyDown(KEY_MAP.Control!, 2);
        await this.client.send('Input.dispatchKeyEvent', {
          type: 'keyDown',
          key: 'a',
          code: 'KeyA',
          windowsVirtualKeyCode: 65,
          modifiers: 2,
        });
        await this.client.send('Input.dispatchKeyEvent', {
          type: 'keyUp',
          key: 'a',
          code: 'KeyA',
          windowsVirtualKeyCode: 65,
          modifiers: 2,
        });
        await this.keyUp(KEY_MAP.Control!, 0);
        // Delete selected text
        await this.keyDown(KEY_MAP.Backspace!);
        await this.keyUp(KEY_MAP.Backspace!);
      }

      // Type text
      if (opts?.fast) {
        await this.client.send('Input.insertText', { text });
      } else {
        const delay = opts?.delay ?? 0;
        for (const char of text) {
          const code = char.charCodeAt(0);
          const keyDef: KeyDef = {
            key: char,
            code: code >= 65 && code <= 90 ? `Key${char}` :
                  code >= 97 && code <= 122 ? `Key${char.toUpperCase()}` :
                  code >= 48 && code <= 57 ? `Digit${char}` :
                  `Key${char}`,
            keyCode: code,
            text: char,
          };
          await this.keyDown(keyDef);
          await this.keyChar(char);
          await this.keyUp(keyDef);

          if (delay > 0) await sleep(delay);
        }
      }

      return ok(el, el.strategy, true, start);
    } catch (err: any) {
      return fail(err.message, el, el.strategy, start);
    }
  }

  /**
   * Press a named key (e.g. "Enter", "Tab", "Escape", "ArrowDown").
   */
  async press(
    key: string,
    opts?: PressOptions,
  ): Promise<ActionResult> {
    const start = Date.now();
    const mods = modifiers(opts);

    const keyDef = KEY_MAP[key] ?? {
      key,
      code: `Key${key.charAt(0).toUpperCase()}${key.slice(1)}`,
      keyCode: key.charCodeAt(0),
      text: key.length === 1 ? key : undefined,
    };

    try {
      // Press modifier keys
      if (opts?.shift) await this.keyDown(KEY_MAP.Shift!, mods);
      if (opts?.ctrl)  await this.keyDown(KEY_MAP.Control!, mods);
      if (opts?.alt)   await this.keyDown(KEY_MAP.Alt!, mods);
      if (opts?.meta)  await this.keyDown(KEY_MAP.Meta!, mods);

      // Press and release the target key
      await this.keyDown(keyDef, mods);
      if (keyDef.text) {
        await this.keyChar(keyDef.text);
      }
      await this.keyUp(keyDef, mods);

      // Release modifier keys
      if (opts?.meta)  await this.keyUp(KEY_MAP.Meta!, 0);
      if (opts?.alt)   await this.keyUp(KEY_MAP.Alt!, 0);
      if (opts?.ctrl)  await this.keyUp(KEY_MAP.Control!, 0);
      if (opts?.shift) await this.keyUp(KEY_MAP.Shift!, 0);

      return ok(null, 'press', true, start);
    } catch (err: any) {
      return fail(err.message, null, 'press', start);
    }
  }

  /**
   * Scroll the page or a specific element.
   */
  async scroll(
    direction: 'up' | 'down' | 'left' | 'right',
    amount = 300,
  ): Promise<ActionResult> {
    const start = Date.now();

    const deltaX =
      direction === 'left' ? -amount : direction === 'right' ? amount : 0;
    const deltaY =
      direction === 'up' ? -amount : direction === 'down' ? amount : 0;

    try {
      // Get the viewport center as the mouse position for the scroll
      const vpResult = await this.client.send('Runtime.evaluate', {
        expression: `JSON.stringify({ x: window.innerWidth / 2, y: window.innerHeight / 2 })`,
        returnByValue: true,
      });
      const vp = JSON.parse(vpResult.result.value);

      await this.client.send('Input.dispatchMouseEvent', {
        type: 'mouseWheel',
        x: vp.x,
        y: vp.y,
        deltaX,
        deltaY,
      });

      return ok(null, 'scroll', true, start);
    } catch (err: any) {
      return fail(err.message, null, 'scroll', start);
    }
  }

  /**
   * Select an option from a <select> element.
   */
  async select(
    target: ElementTarget,
    value: string,
    snapshot: DOMSnapshot,
  ): Promise<ActionResult> {
    const start = Date.now();
    let el: ResolvedElement;
    try {
      el = await this.resolveTarget(target, snapshot);
    } catch (err: any) {
      return fail(err.message, null, 'unknown', start);
    }

    try {
      // Click to focus
      const { x, y } = el.center;
      await this.moveMouse(x, y);
      await this.mouseDown(x, y, 'left', 1);
      await this.mouseUp(x, y, 'left', 1);

      // Set value via JS and fire change event
      const escaped = JSON.stringify(value);
      const js = `
        (function() {
          var el = document.elementFromPoint(${x}, ${y});
          if (!el || el.tagName.toLowerCase() !== 'select') {
            // Walk up to find select
            while (el && el.tagName.toLowerCase() !== 'select') el = el.parentElement;
          }
          if (!el) return false;
          el.value = ${escaped};
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        })()
      `;

      const result = await this.client.send('Runtime.evaluate', {
        expression: js,
        returnByValue: true,
      });

      if (!result.result?.value) {
        return fail('Could not find select element at coordinates', el, el.strategy, start);
      }

      return ok(el, el.strategy, true, start);
    } catch (err: any) {
      return fail(err.message, el, el.strategy, start);
    }
  }

  /**
   * Hover over an element (move mouse without clicking).
   */
  async hover(
    target: ElementTarget,
    snapshot: DOMSnapshot,
  ): Promise<ActionResult> {
    const start = Date.now();
    let el: ResolvedElement;
    try {
      el = await this.resolveTarget(target, snapshot);
    } catch (err: any) {
      return fail(err.message, null, 'unknown', start);
    }

    try {
      await this.moveMouse(el.center.x, el.center.y);
      return ok(el, el.strategy, false, start);
    } catch (err: any) {
      return fail(err.message, el, el.strategy, start);
    }
  }

  /**
   * Drag from one element/location to another.
   */
  async drag(
    from: ElementTarget,
    to: ElementTarget,
    snapshot: DOMSnapshot,
  ): Promise<ActionResult> {
    const start = Date.now();
    let fromEl: ResolvedElement;
    let toEl: ResolvedElement;
    try {
      fromEl = await this.resolveTarget(from, snapshot);
      toEl = await this.resolveTarget(to, snapshot);
    } catch (err: any) {
      return fail(err.message, null, 'unknown', start);
    }

    try {
      // Move to start position
      await this.moveMouse(fromEl.center.x, fromEl.center.y);
      // Press
      await this.mouseDown(fromEl.center.x, fromEl.center.y, 'left', 1);
      // Move to destination (with intermediate steps for smoother drag)
      const steps = 5;
      for (let i = 1; i <= steps; i++) {
        const ratio = i / steps;
        const ix = fromEl.center.x + (toEl.center.x - fromEl.center.x) * ratio;
        const iy = fromEl.center.y + (toEl.center.y - fromEl.center.y) * ratio;
        await this.moveMouse(Math.round(ix), Math.round(iy));
      }
      // Release
      await this.mouseUp(toEl.center.x, toEl.center.y, 'left', 1);

      return ok(fromEl, fromEl.strategy, true, start);
    } catch (err: any) {
      return fail(err.message, fromEl, fromEl.strategy, start);
    }
  }
}
