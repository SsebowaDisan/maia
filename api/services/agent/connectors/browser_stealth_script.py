from __future__ import annotations

STEALTH_INIT_SCRIPT = """
() => {
  // Hide webdriver
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

  // Spoof plugins (headless Chrome has 0 plugins, real Chrome has several)
  const _pluginData = [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => {
      const arr = _pluginData.map((p) => Object.assign(new Plugin(), p));
      arr.length = _pluginData.length;
      return arr;
    }
  });

  // Spoof MIME types
  Object.defineProperty(navigator, 'mimeTypes', {
    get: () => ({ length: 4 })
  });

  // Realistic language settings
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

  // Add chrome runtime (missing in headless mode)
  if (!window.chrome) {
    window.chrome = { runtime: {} };
  }

  // Remove Automation-related properties exposed by CDP
  const _override = (obj, prop) => {
    try { delete obj[prop]; } catch (_) {}
    try { Object.defineProperty(obj, prop, { get: () => undefined }); } catch (_) {}
  };
  _override(window, '__webdriver_evaluate');
  _override(window, '__selenium_evaluate');
  _override(window, '__webdriver_script_function');
  _override(window, '__webdriver_script_func');
  _override(window, '__webdriver_script_fn');
  _override(window, '__fxdriver_evaluate');
  _override(window, '__driver_unwrapped');
  _override(window, '__webdriver_unwrapped');
  _override(window, '__driver_evaluate');
  _override(window, '__selenium_unwrapped');
  _override(window, '__fxdriver_unwrapped');
  _override(document, '$cdc_asdjflasutopfhvcZLmcfl_');
  _override(window, '_Selenium_IDE_Recorder');
  _override(window, '_selenium');
  _override(window, 'calledSelenium');
}
"""
