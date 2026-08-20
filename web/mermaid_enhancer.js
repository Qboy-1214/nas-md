/**
 * Mermaid Diagram Enhancer
 *
 * Wraps each mermaid block with a toolbar:
 *   1. Code / Chart tab toggle (code mode shows "Copy" button)
 *   2. Light / Dark theme toggle for chart area (via CSS filter)
 *   3. Zoom in / out controls + drag-to-pan
 *   4. Download as SVG / PNG
 *
 * DOM structure (sibling insertion, no wrapper replacing original element):
 *   .mme-toolbar          ← inserted BEFORE .language-mermaid
 *   .language-mermaid     ← original element (unchanged in DOM tree)
 *   .mme-code-area        ← inserted AFTER .language-mermaid (hidden by default)
 *
 * Vditor IR-mode click-to-edit is prevented by temporarily removing the
 * vditor-ir__preview class from the ancestor during mousedown on our elements.
 */
(function () {
  'use strict';

  var _blocks = {};

  // ── Source code capture (before Vditor replaces innerHTML) ──
  function captureMermaidSources() {
    var vditor = document.getElementById('vditor');
    if (!vditor) return;
    var areas = vditor.querySelectorAll(
      '.vditor-preview, .vditor-ir__preview, .vditor-sv__preview',
    );
    areas.forEach(function (area) {
      area.querySelectorAll('.language-mermaid').forEach(function (el) {
        if (!el.getAttribute('data-mme-source') && !el.getAttribute('data-processed')) {
          el.setAttribute('data-mme-source', el.textContent);
        }
      });
    });
  }

  // ── Main entry: enhance all rendered mermaid blocks ─────────
  function enhanceAllMermaidBlocks() {
    var vditor = document.getElementById('vditor');
    if (!vditor) return;
    var areas = vditor.querySelectorAll(
      '.vditor-preview, .vditor-ir__preview, .vditor-sv__preview',
    );
    if (!areas.length) return;

    areas.forEach(function (area) {
      area.querySelectorAll('.language-mermaid').forEach(function (el) {
        enhanceBlock(el);
      });
    });
  }

  function enhanceBlock(el) {
    if (el.getAttribute('data-mme-enhanced') === 'true') return;

    // Wait for Vditor to finish rendering
    if (el.getAttribute('data-processed') !== 'true') {
      if (!el.getAttribute('data-mme-source')) {
        el.setAttribute('data-mme-source', el.textContent);
      }
      if (!el._mmeObs) {
        el._mmeObs = new MutationObserver(function () {
          if (el.getAttribute('data-processed') === 'true') {
            el._mmeObs.disconnect();
            delete el._mmeObs;
            enhanceBlock(el);
          }
        });
        el._mmeObs.observe(el, { attributes: true, attributeFilter: ['data-processed'] });
      }
      return;
    }

    var svg = el.querySelector('svg');
    if (!svg) return;

    var sourceCode = el.getAttribute('data-mme-source') || '';
    if (!sourceCode && el.getAttribute('data-code')) {
      sourceCode = el.getAttribute('data-code');
    }

    var blockId = 'mme_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
    _blocks[blockId] = { zoom: 1, theme: 'light', mode: 'chart', sourceCode: sourceCode };

    el.setAttribute('data-mme-enhanced', 'true');
    el.setAttribute('data-mme-id', blockId);

    // Insert toolbar before el, code area after el (siblings, no replaceChild)
    insertUI(el, blockId, sourceCode);
  }

  function insertUI(el, blockId, sourceCode) {
    // Toolbar
    var toolbar = document.createElement('div');
    toolbar.className = 'mme-toolbar';
    toolbar.setAttribute('data-mme-id', blockId);
    toolbar.innerHTML = buildToolbarHTML();
    el.parentNode.insertBefore(toolbar, el);

    // Code area
    var codeArea = document.createElement('pre');
    codeArea.className = 'mme-code-area';
    codeArea.style.display = 'none';
    codeArea.innerHTML = '<code>' + escapeHTML(sourceCode) + '</code>';
    el.parentNode.insertBefore(codeArea, el.nextSibling);

    bindEvents(blockId, toolbar, el, codeArea);
  }

  function escapeHTML(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Toolbar HTML ──────────────────────────────────────────
  function buildToolbarHTML() {
    return (
      '<div class="mme-tabs">' +
      '<button class="mme-tab" data-action="showCode">代码</button>' +
      '<button class="mme-tab active" data-action="showChart">图表</button>' +
      '</div>' +
      '<div class="mme-controls mme-chart-controls">' +
      '<button class="mme-btn" data-action="toggleTheme" title="切换亮色/暗色">' +
      '<svg class="mme-icon-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>' +
      '<svg class="mme-icon-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>' +
      '</button>' +
      '<button class="mme-btn" data-action="zoomIn" title="放大">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>' +
      '</button>' +
      '<button class="mme-btn" data-action="zoomOut" title="缩小">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>' +
      '</button>' +
      '<button class="mme-btn" data-action="toggleFullscreen" title="全屏查看">' +
      '<svg class="mme-icon-fullscreen" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>' +
      '<svg class="mme-icon-exit-fullscreen" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>' +
      '</button>' +
      '<div class="mme-sep"></div>' +
      '<button class="mme-btn" data-action="downloadSVG" title="下载 SVG">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg><span>SVG</span>' +
      '</button>' +
      '<button class="mme-btn" data-action="downloadPNG" title="下载 PNG">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg><span>PNG</span>' +
      '</button>' +
      '</div>' +
      '<div class="mme-controls mme-code-controls" style="display:none">' +
      '<button class="mme-btn" data-action="copyCode" title="复制代码">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>复制</span>' +
      '</button>' +
      '</div>'
    );
  }

  // ── Event binding ────────────────────────────────────────
  function bindEvents(id, toolbar, chartEl, codeEl) {
    // Toolbar button clicks
    toolbar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      handleAction(id, btn.getAttribute('data-action'), toolbar, chartEl, codeEl, btn);
    });

    // Drag-to-pan on chart
    bindDragPan(id, chartEl);

    // Prevent Vditor IR click-to-edit on all our UI elements
    preventVditorClick([toolbar, chartEl, codeEl]);
  }

  function handleAction(id, action, toolbar, chartEl, codeEl, btn) {
    var state = _blocks[id];
    switch (action) {
      case 'showCode':
        setMode(id, 'code', toolbar, chartEl, codeEl);
        break;
      case 'showChart':
        setMode(id, 'chart', toolbar, chartEl, codeEl);
        break;
      case 'toggleTheme':
        toggleTheme(id, toolbar);
        break;
      case 'zoomIn':
        setZoom(id, Math.min(state.zoom + 0.25, 3), chartEl, true);
        break;
      case 'zoomOut':
        setZoom(id, Math.max(state.zoom - 0.25, 0.25), chartEl, true);
        break;
      case 'toggleFullscreen':
        toggleFullscreen(id, toolbar, chartEl);
        break;
      case 'downloadSVG':
        downloadSVG(chartEl);
        break;
      case 'downloadPNG':
        downloadPNG(chartEl);
        break;
      case 'copyCode':
        copyCode(id, btn);
        break;
    }
  }

  // ── Prevent Vditor IR mode click-to-edit ──────────────────
  // Vditor's click handler (bubble phase on .vditor-ir) does two things:
  //   1. fb(target, "vditor-ir__preview") — if found, switches to edit mode
  //   2. B(range, e) — expands the .vditor-ir__node containing the range,
  //      adding .vditor-ir__node--expand class (shows the code)
  //
  // DOM structure for code blocks:
  //   <div class="vditor-ir__node">
  //     <span class="vditor-ir__marker--pre">```mermaid</span>
  //     <div class="vditor-ir__preview">
  //       <code class="language-mermaid" data-mme-enhanced="true">...</code>
  //       .mme-toolbar (sibling, inserted by us)
  //       .mme-code-area (sibling, inserted by us)
  //     </div>
  //   </div>
  //
  // Strategy: Register a click handler in CAPTURE phase on .vditor-ir
  // (fires BEFORE Vditor's bubble handler). For clicks inside our
  // enhanced mermaid block (the .vditor-ir__node that contains our
  // enhanced elements), stop propagation so Vditor's handler never fires.
  // Toolbar button clicks are allowed through.
  function preventVditorClick(elements) {
    if (!elements.length) return;
    var preview = elements[0].closest('.vditor-ir__preview, .vditor-preview, .vditor-sv__preview');
    if (!preview) return;

    // Find the .vditor-ir__node that contains our enhanced block
    var node = preview.closest('.vditor-ir__node');
    if (node) {
      node.setAttribute('data-mme-protected', 'true');
    }
    // Also mark the preview element
    preview.setAttribute('data-mme-protected', 'true');

    // Find the .vditor-ir element where Vditor's click handler lives
    var irElement = preview.closest('.vditor-ir') || preview.closest('.vditor');
    if (!irElement || irElement._mmeClickGuard) return;
    irElement._mmeClickGuard = true;

    irElement.addEventListener(
      'click',
      function (e) {
        // Let toolbar button clicks through — toolbar's own handler
        // will call stopPropagation after handling the action
        var btn = e.target.closest('[data-action]');
        if (btn && btn.closest('.mme-toolbar')) return;

        // Stop clicks inside our protected node (covers toolbar, chart,
        // code area, preview padding, node padding, marker, etc.)
        if (e.target.closest('[data-mme-protected]')) {
          e.stopPropagation();
          return;
        }

        // Click on .vditor-reset padding (left/right of block):
        // Vditor's B(r,e) creates a range from the click position and
        // expands the nearest node. If the click's Y coordinate falls
        // within a protected node's vertical bounds, intercept it.
        if (e.target.classList.contains('vditor-reset')) {
          var nodes = irElement.querySelectorAll('.vditor-ir__node[data-mme-protected]');
          for (var i = 0; i < nodes.length; i++) {
            var rect = nodes[i].getBoundingClientRect();
            if (e.clientY >= rect.top && e.clientY <= rect.bottom) {
              e.stopPropagation();
              return;
            }
          }
        }
      },
      true,
    ); // capture phase — fires before Vditor's bubble handler

    // Also guard against double-click entering edit mode
    irElement.addEventListener(
      'dblclick',
      function (e) {
        if (e.target.closest('[data-mme-protected]')) {
          e.stopPropagation();
        }
      },
      true,
    );
  }

  // ── Drag-to-pan ──────────────────────────────────────────
  function bindDragPan(id, chartEl) {
    var state = _blocks[id];
    var dragging = false,
      startX = 0,
      startY = 0,
      panX = 0,
      panY = 0;

    chartEl.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (chartEl.style.display === 'none') return;
      var svg = chartEl.querySelector('svg');
      if (svg) {
        svg.classList.remove('mme-animating');
        clearTimeout(svg._mmeAnimTimer);
      }
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      state.panX = state.panX || 0;
      state.panY = state.panY || 0;
      panX = state.panX;
      panY = state.panY;
      chartEl.style.cursor = 'grabbing';
      chartEl.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      state.panX = panX + (e.clientX - startX);
      state.panY = panY + (e.clientY - startY);
      applyTransform(id, chartEl);
    });

    document.addEventListener('mouseup', function () {
      if (!dragging) return;
      dragging = false;
      chartEl.style.cursor = 'grab';
      chartEl.style.userSelect = '';
    });

    chartEl.addEventListener('wheel', function (e) {
      if (chartEl.style.display === 'none') return;
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      var delta = e.deltaY < 0 ? 0.1 : -0.1;
      setZoom(id, Math.max(0.25, Math.min(3, state.zoom + delta)), chartEl, false);
    });

    chartEl.style.cursor = 'grab';
  }

  function applyTransform(id, chartEl) {
    var state = _blocks[id];
    var svg = chartEl.querySelector('svg');
    if (!svg) return;
    svg.style.transform =
      'translate3d(' +
      (state.panX || 0) +
      'px, ' +
      (state.panY || 0) +
      'px, 0px) scale(' +
      state.zoom +
      ')';
    svg.style.transformOrigin = 'top left';
  }

  // ── Mode toggle ──────────────────────────────────────────
  function setMode(id, mode, toolbar, chartEl, codeEl) {
    _blocks[id].mode = mode;
    var chartCtrls = toolbar.querySelector('.mme-chart-controls');
    var codeCtrls = toolbar.querySelector('.mme-code-controls');

    toolbar.querySelectorAll('.mme-tab').forEach(function (t) {
      t.classList.toggle('active', t.getAttribute('data-action') === 'show' + capitalize(mode));
    });

    if (mode === 'code') {
      chartEl.style.display = 'none';
      codeEl.style.display = '';
      chartCtrls.style.display = 'none';
      codeCtrls.style.display = '';
    } else {
      chartEl.style.display = '';
      codeEl.style.display = 'none';
      chartCtrls.style.display = '';
      codeCtrls.style.display = 'none';
    }
  }

  // ── Theme toggle (CSS filter based) ──────────────────────
  function toggleTheme(id, toolbar) {
    var state = _blocks[id];
    var newTheme = state.theme === 'light' ? 'dark' : 'light';
    state.theme = newTheme;
    toolbar.setAttribute('data-mme-theme', newTheme);

    var sunIcon = toolbar.querySelector('.mme-icon-sun');
    var moonIcon = toolbar.querySelector('.mme-icon-moon');
    if (sunIcon) sunIcon.style.display = newTheme === 'dark' ? 'none' : '';
    if (moonIcon) moonIcon.style.display = newTheme === 'dark' ? '' : 'none';
  }

  function setZoom(id, zoom, chartEl, animate) {
    _blocks[id].zoom = zoom;
    if (animate) {
      var svg = chartEl.querySelector('svg');
      if (svg) {
        svg.classList.add('mme-animating');
        clearTimeout(svg._mmeAnimTimer);
        svg._mmeAnimTimer = setTimeout(function () {
          svg.classList.remove('mme-animating');
        }, 220);
      }
    }
    applyTransform(id, chartEl);
  }

  // ── Fullscreen toggle ──────────────────────────────────────
  function toggleFullscreen(id, toolbar, chartEl) {
    var wrapper = toolbar.closest('[data-mme-protected]');
    if (!wrapper) wrapper = toolbar.parentElement;
    var isFs = wrapper.classList.toggle('mme-fullscreen');

    var iconFs = toolbar.querySelector('.mme-icon-fullscreen');
    var iconExit = toolbar.querySelector('.mme-icon-exit-fullscreen');
    if (iconFs) iconFs.style.display = isFs ? 'none' : '';
    if (iconExit) iconExit.style.display = isFs ? '' : 'none';

    var btn = toolbar.querySelector('[data-action="toggleFullscreen"]');
    if (btn) btn.title = isFs ? '退出全屏' : '全屏查看';

    // ESC key listener to exit fullscreen
    if (isFs) {
      wrapper._mmeEscHandler = function (e) {
        if (e.key === 'Escape' && wrapper.classList.contains('mme-fullscreen')) {
          toggleFullscreen(id, toolbar, chartEl);
        }
      };
      document.addEventListener('keydown', wrapper._mmeEscHandler);
    } else if (wrapper._mmeEscHandler) {
      document.removeEventListener('keydown', wrapper._mmeEscHandler);
      delete wrapper._mmeEscHandler;
    }
  }

  // ── Copy code ────────────────────────────────────────────
  function copyCode(id, btn) {
    var text = _blocks[id].sourceCode || '';
    var span = btn.querySelector('span');
    var doFlash = function () {
      if (!span) return;
      var orig = span.textContent;
      span.textContent = '\u5df2\u590d\u5236';
      btn.classList.add('mme-copied');
      setTimeout(function () {
        span.textContent = orig;
        btn.classList.remove('mme-copied');
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(doFlash)
        .catch(function () {
          fallbackCopy(text);
          doFlash();
        });
    } else {
      fallbackCopy(text);
      doFlash();
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch (_) {}
    document.body.removeChild(ta);
  }

  // ── Download SVG ─────────────────────────────────────────
  function downloadSVG(chartEl) {
    var svg = chartEl.querySelector('svg');
    if (!svg) {
      toast('\u65e0\u6cd5\u83b7\u53d6\u56fe\u8868');
      return;
    }
    var clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var bbox = svg.getBoundingClientRect();
    clone.setAttribute('width', Math.round(bbox.width));
    clone.setAttribute('height', Math.round(bbox.height));
    var blob = new Blob([new XMLSerializer().serializeToString(clone)], {
      type: 'image/svg+xml;charset=utf-8',
    });
    saveBlob(blob, 'diagram.svg');
  }

  // ── Download PNG ─────────────────────────────────────────
  function downloadPNG(chartEl) {
    var svg = chartEl.querySelector('svg');
    if (!svg) {
      toast('\u65e0\u6cd5\u83b7\u53d6\u56fe\u8868');
      return;
    }
    var clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var bbox = svg.getBoundingClientRect();
    var w = Math.ceil(bbox.width),
      h = Math.ceil(bbox.height),
      scale = window.devicePixelRatio || 2;
    clone.setAttribute('width', w);
    clone.setAttribute('height', h);
    var data = new XMLSerializer().serializeToString(clone);
    var url = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(data)));
    var img = new Image();
    img.onload = function () {
      var c = document.createElement('canvas');
      c.width = w * scale;
      c.height = h * scale;
      var ctx = c.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, w, h);
      c.toBlob(function (b) {
        saveBlob(b, 'diagram.png');
      }, 'image/png');
    };
    img.onerror = function () {
      toast('PNG \u5bfc\u51fa\u5931\u8d25');
    };
    img.src = url;
  }

  // ── Utilities ────────────────────────────────────────────
  function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function saveBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function toast(msg) {
    var t = document.getElementById('toast');
    if (t) {
      t.textContent = msg;
      t.style.display = '';
      setTimeout(function () {
        t.style.display = 'none';
      }, 2500);
    } else alert(msg);
  }

  // Public API
  window._enhanceMermaid = enhanceAllMermaidBlocks;
  window._captureMermaidSources = captureMermaidSources;
})();
