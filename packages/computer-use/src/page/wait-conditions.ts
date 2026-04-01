// ---------------------------------------------------------------------------
// Wait Conditions – smart waiting via CDP polling and events
// ---------------------------------------------------------------------------

import type { CDPClient } from './dom-snapshot';

// ---- Public types ---------------------------------------------------------

export type WaitCondition =
  | { text: string }
  | { element: string }
  | { elementGone: string }
  | { navigation: true }
  | { networkIdle: number }
  | { urlContains: string }
  | { titleContains: string }
  | { domStable: number }
  | { custom: string };

// ---- Helpers --------------------------------------------------------------

const POLL_INTERVAL = 200;

async function evaluateBool(
  client: CDPClient,
  expression: string,
): Promise<boolean> {
  const result = await client.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
  });
  if (result.exceptionDetails) return false;
  return !!result.result.value;
}

function timeoutError(condition: string, timeoutMs: number): Error {
  return new Error(
    `Wait condition timed out after ${timeoutMs}ms: ${condition}`,
  );
}

/**
 * Generic poller: calls `check` every `interval` ms until it returns true
 * or `timeout` ms elapse.
 */
function poll(
  check: () => Promise<boolean>,
  timeout: number,
  label: string,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const deadline = Date.now() + timeout;
    let timer: ReturnType<typeof setInterval>;

    const tick = async () => {
      try {
        if (await check()) {
          clearInterval(timer);
          resolve();
          return;
        }
      } catch {
        // swallow – next tick will retry
      }
      if (Date.now() >= deadline) {
        clearInterval(timer);
        reject(timeoutError(label, timeout));
      }
    };

    timer = setInterval(tick, POLL_INTERVAL);
    // Run first check immediately
    tick();
  });
}

// ---- Condition implementations --------------------------------------------

async function waitForText(
  client: CDPClient,
  text: string,
  timeout: number,
): Promise<void> {
  const escaped = JSON.stringify(text);
  await poll(
    () =>
      evaluateBool(
        client,
        `document.body && document.body.innerText.includes(${escaped})`,
      ),
    timeout,
    `text "${text}"`,
  );
}

async function waitForElement(
  client: CDPClient,
  selector: string,
  timeout: number,
): Promise<void> {
  const escaped = JSON.stringify(selector);
  await poll(
    () =>
      evaluateBool(
        client,
        `!!document.querySelector(${escaped})`,
      ),
    timeout,
    `element "${selector}"`,
  );
}

async function waitForElementGone(
  client: CDPClient,
  selector: string,
  timeout: number,
): Promise<void> {
  const escaped = JSON.stringify(selector);
  await poll(
    () =>
      evaluateBool(
        client,
        `!document.querySelector(${escaped})`,
      ),
    timeout,
    `element gone "${selector}"`,
  );
}

async function waitForNavigation(
  client: CDPClient,
  timeout: number,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let resolved = false;
    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        // Attempt to remove the binding – best-effort
        reject(timeoutError('navigation', timeout));
      }
    }, timeout);

    // Listen for frameNavigated by enabling Page domain events.
    // We use a Runtime binding to bridge CDP events to our promise.
    const bindingName = '__maia_nav_' + Date.now();

    (async () => {
      try {
        await client.send('Page.enable');
        await client.send('Runtime.addBinding', { name: bindingName });
        await client.send('Runtime.evaluate', {
          expression: `
            (function() {
              var orig = window.location.href;
              var iv = setInterval(function() {
                if (window.location.href !== orig) {
                  clearInterval(iv);
                  window['${bindingName}']('done');
                }
              }, 100);
              // Also listen for popstate / hashchange
              window.addEventListener('popstate', function() {
                clearInterval(iv);
                window['${bindingName}']('done');
              }, { once: true });
            })()
          `,
        });

        // Poll location as a fallback (the binding may not fire in all cases)
        const origResult = await client.send('Runtime.evaluate', {
          expression: 'window.location.href',
          returnByValue: true,
        });
        const origUrl = origResult.result?.value || '';

        await poll(
          async () => {
            const r = await client.send('Runtime.evaluate', {
              expression: 'window.location.href',
              returnByValue: true,
            });
            return r.result?.value !== origUrl;
          },
          timeout,
          'navigation',
        );

        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          resolve();
        }
      } catch (err) {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          reject(err);
        }
      }
    })();
  });
}

async function waitForNetworkIdle(
  client: CDPClient,
  quietMs: number,
  timeout: number,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let lastActivity = Date.now();
    let inflight = 0;
    let resolved = false;

    const deadline = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        reject(timeoutError(`networkIdle(${quietMs}ms)`, timeout));
      }
    }, timeout);

    // Enable network tracking
    client.send('Network.enable').then(() => {
      // Track requests
      const checkIdle = setInterval(async () => {
        if (resolved) {
          clearInterval(checkIdle);
          return;
        }
        if (inflight === 0 && Date.now() - lastActivity >= quietMs) {
          resolved = true;
          clearInterval(checkIdle);
          clearTimeout(deadline);
          await client.send('Network.disable').catch(() => {});
          resolve();
        }
      }, POLL_INTERVAL);

      // We cannot directly subscribe to CDP events with a send-only client,
      // so poll pending request count via JS.
      const pollNet = setInterval(async () => {
        if (resolved) {
          clearInterval(pollNet);
          return;
        }
        try {
          const r = await client.send('Runtime.evaluate', {
            expression: `
              (function() {
                if (!window.__maiaNetCount) {
                  window.__maiaNetCount = 0;
                  var origFetch = window.fetch;
                  window.fetch = function() {
                    window.__maiaNetCount++;
                    return origFetch.apply(this, arguments).finally(function() {
                      window.__maiaNetCount--;
                    });
                  };
                  var origOpen = XMLHttpRequest.prototype.open;
                  var origSend = XMLHttpRequest.prototype.send;
                  XMLHttpRequest.prototype.send = function() {
                    window.__maiaNetCount++;
                    this.addEventListener('loadend', function() { window.__maiaNetCount--; });
                    return origSend.apply(this, arguments);
                  };
                }
                return window.__maiaNetCount;
              })()
            `,
            returnByValue: true,
          });
          const count = r.result?.value ?? 0;
          if (count > 0) {
            lastActivity = Date.now();
            inflight = count;
          } else {
            inflight = 0;
          }
        } catch {
          // swallow
        }
      }, POLL_INTERVAL);
    }).catch((err) => {
      if (!resolved) {
        resolved = true;
        clearTimeout(deadline);
        reject(err);
      }
    });
  });
}

async function waitForUrlContains(
  client: CDPClient,
  fragment: string,
  timeout: number,
): Promise<void> {
  const escaped = JSON.stringify(fragment);
  await poll(
    () =>
      evaluateBool(
        client,
        `window.location.href.includes(${escaped})`,
      ),
    timeout,
    `urlContains "${fragment}"`,
  );
}

async function waitForTitleContains(
  client: CDPClient,
  fragment: string,
  timeout: number,
): Promise<void> {
  const escaped = JSON.stringify(fragment);
  await poll(
    () =>
      evaluateBool(
        client,
        `document.title.includes(${escaped})`,
      ),
    timeout,
    `titleContains "${fragment}"`,
  );
}

async function waitForDomStable(
  client: CDPClient,
  quietMs: number,
  timeout: number,
): Promise<void> {
  // Inject a MutationObserver and poll its last-change timestamp
  const setupJs = `
    (function() {
      if (!window.__maiaDomStable) {
        window.__maiaDomLastMut = Date.now();
        window.__maiaDomStable = new MutationObserver(function() {
          window.__maiaDomLastMut = Date.now();
        });
        window.__maiaDomStable.observe(document.body, {
          childList: true, subtree: true, attributes: true, characterData: true
        });
      }
      return true;
    })()
  `;

  await client.send('Runtime.evaluate', {
    expression: setupJs,
    returnByValue: true,
  });

  await poll(
    async () => {
      const r = await client.send('Runtime.evaluate', {
        expression: `Date.now() - (window.__maiaDomLastMut || 0)`,
        returnByValue: true,
      });
      const elapsed = r.result?.value ?? 0;
      return elapsed >= quietMs;
    },
    timeout,
    `domStable(${quietMs}ms)`,
  );
}

async function waitForCustom(
  client: CDPClient,
  expression: string,
  timeout: number,
): Promise<void> {
  await poll(
    () => evaluateBool(client, `!!(${expression})`),
    timeout,
    `custom: ${expression.slice(0, 60)}`,
  );
}

// ---- Public API -----------------------------------------------------------

/**
 * Wait for a condition to be met on the page.
 *
 * @param client  CDP client
 * @param condition  What to wait for
 * @param timeout  Max wait in ms (default 10 000)
 */
export async function waitFor(
  client: CDPClient,
  condition: WaitCondition,
  timeout = 10_000,
): Promise<void> {
  if ('text' in condition) {
    return waitForText(client, condition.text, timeout);
  }
  if ('element' in condition) {
    return waitForElement(client, condition.element, timeout);
  }
  if ('elementGone' in condition) {
    return waitForElementGone(client, condition.elementGone, timeout);
  }
  if ('navigation' in condition) {
    return waitForNavigation(client, timeout);
  }
  if ('networkIdle' in condition) {
    return waitForNetworkIdle(client, condition.networkIdle, timeout);
  }
  if ('urlContains' in condition) {
    return waitForUrlContains(client, condition.urlContains, timeout);
  }
  if ('titleContains' in condition) {
    return waitForTitleContains(client, condition.titleContains, timeout);
  }
  if ('domStable' in condition) {
    return waitForDomStable(client, condition.domStable, timeout);
  }
  if ('custom' in condition) {
    return waitForCustom(client, condition.custom, timeout);
  }

  throw new Error('Unknown wait condition');
}
