function onBlockLoad() {
  var infor_panel_scroll_pos = 0;
  globalThis.createModal = () => {
    // Create modal for the 1st time if it does not exist
    var modal = document.getElementById("pdf-modal");
    var old_position = null;
    var old_width = null;
    var old_left = null;
    var expanded = false;

    modal.id = "pdf-modal";
    modal.className = "modal";
    modal.innerHTML = `
            <div class="modal-content">
              <div class="modal-header">
                <span class="close" id="modal-close">&times;</span>
                <span class="close" id="modal-expand">&#x26F6;</span>
              </div>
              <div class="modal-body">
                <pdfjs-viewer-element id="pdf-viewer" viewer-path="GR_FILE_ROOT_PATH/file=PDFJS_PREBUILT_DIR" locale="en" phrase="true">
                </pdfjs-viewer-element>
              </div>
            </div>
          `;

    modal.querySelector("#modal-close").onclick = function () {
      modal.style.display = "none";
      clearBboxHighlights();
      clearSearchHighlights();
      var info_panel = document.getElementById("html-info-panel");
      if (info_panel) {
        info_panel.style.display = "block";
      }
      var scrollableDiv = document.getElementById("chat-info-panel");
      scrollableDiv.scrollTop = infor_panel_scroll_pos;
    };

    modal.querySelector("#modal-expand").onclick = function () {
      expanded = !expanded;
      if (expanded) {
        old_position = modal.style.position;
        old_left = modal.style.left;
        old_width = modal.style.width;

        modal.style.position = "fixed";
        modal.style.width = "70%";
        modal.style.left = "15%";
        modal.style.height = "100dvh";
      } else {
        modal.style.position = old_position;
        modal.style.width = old_width;
        modal.style.left = old_left;
        modal.style.height = "85dvh";
      }
    };
  };

  function clamp01(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return Math.max(0, Math.min(1, numeric));
  }

  function getInnerDoc() {
    var viewer = document.querySelector("#pdf-viewer");
    var iframe = viewer ? viewer.iframe : null;
    if (!iframe) {
      return null;
    }
    return iframe.contentDocument ? iframe.contentDocument : iframe.contentWindow.document;
  }

  function getPdfViewerApp() {
    var innerDoc = getInnerDoc();
    if (!innerDoc || !innerDoc.defaultView) {
      return null;
    }
    var win = innerDoc.defaultView;
    return win.PDFViewerApplication || null;
  }

  function normalizeSearchPhrase(raw) {
    var text = String(raw || "")
      .replace(/[\u3010\[]\d+[\u3011\]]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) {
      return "";
    }
    if (text.toLowerCase() === "true" || text.toLowerCase() === "false") {
      return "";
    }
    if (text.length > 360) {
      return text.slice(0, 360);
    }
    return text;
  }

  function dedupePhrases(rawPhrases) {
    var seen = new Set();
    var out = [];
    for (var i = 0; i < rawPhrases.length; i++) {
      var normalized = normalizeSearchPhrase(rawPhrases[i]);
      if (!normalized) {
        continue;
      }
      var key = normalized.toLowerCase();
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      out.push(normalized);
      if (out.length >= 12) {
        break;
      }
    }
    return out;
  }

  function parseSearchPayload(raw) {
    var value = String(raw || "").trim();
    if (!value) {
      return [];
    }
    try {
      var parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item || ""));
      }
      if (typeof parsed === "string") {
        return [parsed];
      }
    } catch (_error) {
      // Treat as plain text if payload is not JSON.
    }
    return value.split(/\s*\|\|\s*|\r?\n|;\s*/g).filter(Boolean);
  }

  function extractMarkedSearchPhrases(target) {
    var terms = [];
    var detailsNode = target.closest("details");
    var scope = detailsNode || target.closest(".evidence") || document;
    var marks = scope.querySelectorAll("mark");
    for (var i = 0; i < marks.length; i++) {
      terms.push(marks[i].textContent || "");
      if (terms.length >= 12) {
        break;
      }
    }
    return terms;
  }

  function resolveSearchPhrases(target) {
    var terms = [];
    var searchAttr = target.getAttribute("data-search");
    var phraseAttr = target.getAttribute("data-phrase");
    terms = terms.concat(parseSearchPayload(searchAttr));
    terms = terms.concat(parseSearchPayload(phraseAttr));
    terms = terms.concat(extractMarkedSearchPhrases(target));
    return dedupePhrases(terms);
  }

  function parseBboxes(raw) {
    var payload = String(raw || "").trim();
    if (!payload) {
      return [];
    }
    payload = payload.replace(/&quot;/g, '"').replace(/&#34;/g, '"');
    var parsed = null;
    try {
      parsed = JSON.parse(payload);
    } catch (_error) {
      return [];
    }
    if (!Array.isArray(parsed)) {
      return [];
    }
    var boxes = [];
    for (var i = 0; i < parsed.length; i++) {
      var row = parsed[i];
      if (!row || typeof row !== "object") {
        continue;
      }
      var x = clamp01(row.x);
      var y = clamp01(row.y);
      var width = Math.max(0, Math.min(1 - x, Number(row.width || 0)));
      var height = Math.max(0, Math.min(1 - y, Number(row.height || 0)));
      if (width < 0.002 || height < 0.002) {
        continue;
      }
      boxes.push({
        x: Number(x.toFixed(6)),
        y: Number(y.toFixed(6)),
        width: Number(width.toFixed(6)),
        height: Number(height.toFixed(6)),
      });
      if (boxes.length >= 24) {
        break;
      }
    }
    return boxes;
  }

  function clearBboxHighlights() {
    var innerDoc = getInnerDoc();
    if (!innerDoc) {
      return;
    }
    var layers = innerDoc.querySelectorAll(".maia-bbox-layer");
    for (var i = 0; i < layers.length; i++) {
      layers[i].remove();
    }
  }

  function clearTextLayerHighlights() {
    var innerDoc = getInnerDoc();
    if (!innerDoc) {
      return;
    }
    var highlightedNodes = innerDoc.querySelectorAll(".textLayer .highlight");
    for (var i = 0; i < highlightedNodes.length; i++) {
      highlightedNodes[i].classList.remove(
        "highlight",
        "selected",
        "begin",
        "middle",
        "end",
        "appended"
      );
    }
  }

  function clearSearchHighlights() {
    clearTextLayerHighlights();
    var app = getPdfViewerApp();
    var eventBus = app ? app.eventBus : null;
    if (!eventBus) {
      return;
    }
    eventBus.dispatch("find", {
      source: window,
      type: "",
      query: "",
      caseSensitive: false,
      entireWord: false,
      highlightAll: false,
      findPrevious: false,
      matchDiacritics: false,
    });
  }

  function buildFindQuery(search_phrases, phrase_search) {
    if (!Array.isArray(search_phrases) || search_phrases.length === 0) {
      return "";
    }
    var tokens = [];
    for (var i = 0; i < search_phrases.length; i++) {
      var phrase = normalizeSearchPhrase(search_phrases[i]);
      if (!phrase) {
        continue;
      }
      if (phrase_search) {
        tokens.push(phrase);
      } else {
        tokens = tokens.concat(phrase.match(/\S+/g) || []);
      }
      if (tokens.length >= 16) {
        break;
      }
    }
    tokens = dedupePhrases(tokens);
    if (tokens.length === 0) {
      return "";
    }
    if (tokens.length === 1) {
      return tokens[0];
    }
    return tokens;
  }

  globalThis.searchPdfText = (search_phrases, page_label, phrase_search, attempt = 0) => {
    var app = getPdfViewerApp();
    var eventBus = app ? app.eventBus : null;
    if (!app || !eventBus) {
      if (attempt < 30) {
        setTimeout(
          () => searchPdfText(search_phrases, page_label, phrase_search, attempt + 1),
          180
        );
      }
      return;
    }

    var pageNumber = Number(page_label);
    if (Number.isFinite(pageNumber) && pageNumber > 0) {
      if (app.pdfLinkService && typeof app.pdfLinkService.goToPage === "function") {
        app.pdfLinkService.goToPage(pageNumber);
      } else if (app.pdfViewer) {
        app.pdfViewer.currentPageNumber = pageNumber;
      }
    }

    var query = buildFindQuery(search_phrases, phrase_search);
    clearSearchHighlights();
    if (!query || (Array.isArray(query) && query.length === 0)) {
      return;
    }

    eventBus.dispatch("find", {
      source: window,
      type: "",
      query: query,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: false,
      matchDiacritics: false,
    });
  };

  globalThis.renderBboxHighlights = (boxes, page_label, attempt = 0) => {
    var innerDoc = getInnerDoc();
    if (!innerDoc) {
      if (attempt < 30) {
        setTimeout(() => renderBboxHighlights(boxes, page_label, attempt + 1), 180);
      }
      return;
    }

    var page_selector = "#viewer > div[data-page-number='" + page_label + "']";
    var pageNode = innerDoc.querySelector(page_selector);
    if (!pageNode) {
      if (attempt < 30) {
        setTimeout(() => renderBboxHighlights(boxes, page_label, attempt + 1), 180);
      }
      return;
    }

    var oldLayer = pageNode.querySelector(".maia-bbox-layer");
    if (oldLayer) {
      oldLayer.remove();
    }
    pageNode.style.position = "relative";

    var layer = innerDoc.createElement("div");
    layer.className = "maia-bbox-layer";
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var rect = innerDoc.createElement("div");
      rect.className = "maia-bbox-rect";
      rect.style.left = box.x * 100 + "%";
      rect.style.top = box.y * 100 + "%";
      rect.style.width = box.width * 100 + "%";
      rect.style.height = box.height * 100 + "%";
      layer.appendChild(rect);
    }
    pageNode.appendChild(layer);
  };

  // Sleep function using Promise and setTimeout
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // Function to open modal and display PDF
  globalThis.openModal = async (event) => {
    event.preventDefault();
    var target = event.currentTarget;
    var src = target.getAttribute("data-src");
    var page = target.getAttribute("data-page");
    var phrase_mode = String(target.getAttribute("data-phrase") || "").toLowerCase() !== "false";
    var bboxes_raw = target.getAttribute("data-bboxes") || target.getAttribute("data-boxes");
    var bboxes = parseBboxes(bboxes_raw);
    var search_phrases = resolveSearchPhrases(target);

    var pdfViewer = document.getElementById("pdf-viewer");

    var current_src = pdfViewer.getAttribute("src");
    if (current_src != src) {
      pdfViewer.setAttribute("src", src);
    }
    pdfViewer.setAttribute("page", page);

    var scrollableDiv = document.getElementById("chat-info-panel");
    infor_panel_scroll_pos = scrollableDiv.scrollTop;

    var modal = document.getElementById("pdf-modal");
    modal.style.display = "block";
    var info_panel = document.getElementById("html-info-panel");
    if (info_panel) {
      info_panel.style.display = "none";
    }
    scrollableDiv.scrollTop = 0;

    await sleep(500);
    clearSearchHighlights();
    if (bboxes.length > 0) {
      clearBboxHighlights();
      renderBboxHighlights(bboxes, page);
    } else {
      clearBboxHighlights();
      searchPdfText(search_phrases, page, phrase_mode);
    }
  };

  globalThis.assignPdfOnclickEvent = () => {
    // Get all links and attach click event
    var links = document.getElementsByClassName("pdf-link");
    for (var i = 0; i < links.length; i++) {
      links[i].onclick = openModal;
    }
  };

  var created_modal = document.getElementById("pdf-viewer");
  if (!created_modal) {
    createModal();
  }
}
