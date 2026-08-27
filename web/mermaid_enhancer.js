/**
 * Mermaid Diagram Enhancer - Overlay Version
 *
 * This version uses a completely separate overlay layer outside Vditor's DOM
 * to absolutely position the toolbars and code areas over the mermaid charts.
 * This guarantees zero interference with Vditor's Lute engine and DOM diffing algorithm.
 */
(function () {
  'use strict';

  var _blocks = {};
  var _overlayLayer = null;

  function initOverlayLayer() {
    if (_overlayLayer) return _overlayLayer;
    _overlayLayer = document.createElement('div');
    _overlayLayer.className = 'mme-global-overlay';
    _overlayLayer.style.position = 'absolute';
    _overlayLayer.style.top = '0';
    _overlayLayer.style.left = '0';
    _overlayLayer.style.width = '100%';
    _overlayLayer.style.height = '100%';
    _overlayLayer.style.pointerEvents = 'none'; // Let clicks pass through except on our UI
    _overlayLayer.style.zIndex = '1000';
    
    // We attach it to the vditor container so it scrolls with it
    var vditorContainer = document.querySelector('.vditor-content') || document.querySelector('.vditor');
    if (vditorContainer) {
      if (getComputedStyle(vditorContainer).position === 'static') {
        vditorContainer.style.position = 'relative';
      }
      vditorContainer.appendChild(_overlayLayer);
    }
    
    // Aggressive DOM sanitizer for Vditor's native Undo bug in IR mode
    // When Ctrl+Z is pressed, Vditor's undo stack sometimes restores corrupted HTML
    // containing .vditor-wysiwyg__block inside .vditor-ir__node.
    var irContainer = document.querySelector('.vditor-ir');
    if (irContainer) {
      if (!window._mmeSanitizerObserver) {
        window._mmeSanitizerObserver = new MutationObserver(function(mutations) {
          var hasCorruption = false;
          mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length > 0) {
              for (var i = 0; i < mutation.addedNodes.length; i++) {
                var node = mutation.addedNodes[i];
                if (node.nodeType === 1) { // Element
                  if (node.classList && node.classList.contains('vditor-wysiwyg__block')) {
                    hasCorruption = true;
                  } else if (node.querySelector && node.querySelector('.vditor-wysiwyg__block')) {
                    hasCorruption = true;
                  }
                }
              }
            }
          });
          if (hasCorruption) {
            var badBlocks = irContainer.querySelectorAll('.vditor-wysiwyg__block');
            if (badBlocks.length > 0) {
              console.log('[mermaid-enhancer] Sanitizing native Vditor undo corruption:', badBlocks.length, 'blocks removed');
              badBlocks.forEach(function(el) { el.remove(); });
            }
          }
        });
        window._mmeSanitizerObserver.observe(irContainer, { childList: true, subtree: true });
      }
    }

    function loop() {
      updateOverlayPositions();
      _trackingTimer = requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    
    return _overlayLayer;
  }

  function updateOverlayPositions() {
    if (!_overlayLayer) return;
    var uis = _overlayLayer.querySelectorAll('.mme-overlay-item');
    uis.forEach(function(ui) {
      var blockId = ui.getAttribute('data-mme-id');
      var state = _blocks[blockId];
      if (!state || !state.targetEl || !document.contains(state.targetEl)) {
        // Target element is gone (e.g. Vditor re-rendered it)
        ui.remove();
        delete _blocks[blockId];
        return;
      }
      
      var target = state.targetEl;
      // We position the UI relative to the overlay layer's offsetParent
      var targetRect = target.getBoundingClientRect();
      var layerRect = _overlayLayer.getBoundingClientRect();
      
      var toolbar = ui.querySelector('.mme-toolbar');
      var toolbarHeight = toolbar ? toolbar.offsetHeight : 38;
      
      var top = targetRect.top - layerRect.top - toolbarHeight;
      var left = targetRect.left - layerRect.left;
      
      ui.style.top = top + 'px';
      ui.style.left = left + 'px';
      ui.style.width = targetRect.width + 'px';
      // height is dynamic
    });
  }

  function captureMermaidSources() {
    var vditor = document.getElementById('vditor');
    if (!vditor) return;
    var areas = vditor.querySelectorAll('.vditor-preview, .vditor-ir__preview, .vditor-sv__preview');
    areas.forEach(function (area) {
      area.querySelectorAll('.language-mermaid').forEach(function (el) {
        if (!el.getAttribute('data-mme-source') && !el.getAttribute('data-processed')) {
          el.setAttribute('data-mme-source', el.textContent);
        }
      });
    });
  }

  function enhanceAllMermaidBlocks() {
    var vditor = document.getElementById('vditor');
    if (!vditor) return;
    initOverlayLayer();
    
    var areas = vditor.querySelectorAll('.vditor-preview, .vditor-ir__preview, .vditor-sv__preview');
    if (!areas.length) return;

    areas.forEach(function (area) {
      area.querySelectorAll('.language-mermaid').forEach(function (el) {
        enhanceBlock(el);
      });
    });
  }

  function enhanceBlock(el) {
    if (el.getAttribute('data-mme-enhanced') === 'true') {
        // Just verify if its UI still exists
        var blockId = el.getAttribute('data-mme-id');
        if (blockId && _overlayLayer && !_overlayLayer.querySelector('[data-mme-id="'+blockId+'"]')) {
            el.setAttribute('data-mme-enhanced', 'false');
        } else {
            return;
        }
    }

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
    _blocks[blockId] = { zoom: 1, theme: 'light', mode: 'chart', sourceCode: sourceCode, targetEl: el };

    el.setAttribute('data-mme-enhanced', 'true');
    el.setAttribute('data-mme-id', blockId);

    insertOverlayUI(el, blockId, sourceCode);
  }

  function insertOverlayUI(el, blockId, sourceCode) {
    if (!_overlayLayer) return;
    
    var uiContainer = document.createElement('div');
    uiContainer.className = 'mme-overlay-item';
    uiContainer.setAttribute('data-mme-id', blockId);
    uiContainer.style.position = 'absolute';
    uiContainer.style.pointerEvents = 'none'; // Let clicks pass to the SVG
    uiContainer.style.display = 'flex';
    uiContainer.style.flexDirection = 'column';
    uiContainer.style.alignItems = 'stretch';
    
    // Toolbar
    var toolbar = document.createElement('div');
    toolbar.className = 'mme-toolbar';
    toolbar.style.pointerEvents = 'auto'; // Re-enable clicks for our UI
    toolbar.innerHTML = buildToolbarHTML();
    uiContainer.appendChild(toolbar);

    // Code area
    var codeArea = document.createElement('div');
    codeArea.className = 'mme-code-area';
    codeArea.style.display = 'none';
    codeArea.style.pointerEvents = 'auto'; // Re-enable clicks for our UI
    codeArea.innerHTML = '<span class="mme-code-content">' + escapeHTML(sourceCode) + '</span>';
    uiContainer.appendChild(codeArea);

    _overlayLayer.appendChild(uiContainer);
    bindEvents(blockId, toolbar, el, codeArea, uiContainer);
    
    // Hide Vditor's chart when in code mode
    // We do this by toggling visibility of the svg
    el._mmeSvg = el.querySelector('svg');
  }

  function escapeHTML(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

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

  function bindEvents(id, toolbar, chartEl, codeEl, uiContainer) {
    toolbar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      handleAction(id, btn.getAttribute('data-action'), toolbar, chartEl, codeEl, btn);
    });

    bindDragPan(id, chartEl);
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
        toggleTheme(id, toolbar, chartEl);
        break;
      case 'zoomIn':
        setZoom(id, Math.min(state.zoom + 0.25, 3), chartEl, true);
        break;
      case 'zoomOut':
        setZoom(id, Math.max(state.zoom - 0.25, 0.25), chartEl, true);
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

  function bindDragPan(id, chartEl) {
    var state = _blocks[id];
    var dragging = false, startX = 0, startY = 0, panX = 0, panY = 0;

    // We bind drag to the chartEl, which is still in the main DOM
    chartEl.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (state.mode === 'code') return;
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
      e.stopPropagation(); // Prevent Vditor from intercepting
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
      if (state.mode === 'code') return;
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      e.stopPropagation();
      var delta = e.deltaY < 0 ? 0.1 : -0.1;
      setZoom(id, Math.max(0.25, Math.min(3, state.zoom + delta)), chartEl, false);
    });

    chartEl.style.cursor = 'grab';
  }

  function applyTransform(id, chartEl) {
    var state = _blocks[id];
    var svg = chartEl.querySelector('svg');
    if (!svg) return;
    svg.style.transform = 'translate3d(' + (state.panX || 0) + 'px, ' + (state.panY || 0) + 'px, 0px) scale(' + state.zoom + ')';
    svg.style.transformOrigin = 'top left';
  }

  function setMode(id, mode, toolbar, chartEl, codeEl) {
    var state = _blocks[id];
    state.mode = mode;
    var chartCtrls = toolbar.querySelector('.mme-chart-controls');
    var codeCtrls = toolbar.querySelector('.mme-code-controls');

    toolbar.querySelectorAll('.mme-tab').forEach(function (t) {
      t.classList.toggle('active', t.getAttribute('data-action') === 'show' + capitalize(mode));
    });

    if (mode === 'code') {
      if (chartEl._mmeSvg) chartEl._mmeSvg.style.opacity = '0'; // Hide chart
      codeEl.style.display = '';
      chartCtrls.style.display = 'none';
      codeCtrls.style.display = '';
    } else {
      if (chartEl._mmeSvg) chartEl._mmeSvg.style.opacity = '1';
      codeEl.style.display = 'none';
      chartCtrls.style.display = '';
      codeCtrls.style.display = 'none';
    }
  }

  function toggleTheme(id, toolbar, chartEl) {
    var state = _blocks[id];
    var newTheme = state.theme === 'light' ? 'dark' : 'light';
    state.theme = newTheme;
    
    // Apply theme filter to the svg
    var svg = chartEl.querySelector('svg');
    if (svg) {
        if (newTheme === 'dark') {
            svg.style.filter = 'invert(0.9) hue-rotate(180deg)';
        } else {
            svg.style.filter = '';
        }
    }

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
      navigator.clipboard.writeText(text).then(doFlash).catch(function () {
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
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }

  function downloadSVG(chartEl) {
    var svg = chartEl.querySelector('svg');
    if (!svg) { toast('\u65e0\u6cd5\u83b7\u53d6\u56fe\u8868'); return; }
    var clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var bbox = svg.getBoundingClientRect();
    clone.setAttribute('width', Math.round(bbox.width));
    clone.setAttribute('height', Math.round(bbox.height));
    var blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' });
    saveBlob(blob, 'diagram.svg');
  }

  function downloadPNG(chartEl) {
    var svg = chartEl.querySelector('svg');
    if (!svg) { toast('\u65e0\u6cd5\u83b7\u53d6\u56fe\u8868'); return; }
    var clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var bbox = svg.getBoundingClientRect();
    var w = Math.ceil(bbox.width), h = Math.ceil(bbox.height), scale = window.devicePixelRatio || 2;
    clone.setAttribute('width', w);
    clone.setAttribute('height', h);
    var data = new XMLSerializer().serializeToString(clone);
    var url = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(data)));
    var img = new Image();
    img.onload = function () {
      var c = document.createElement('canvas');
      c.width = w * scale; c.height = h * scale;
      var ctx = c.getContext('2d');
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
      ctx.scale(scale, scale); ctx.drawImage(img, 0, 0, w, h);
      c.toBlob(function (b) { saveBlob(b, 'diagram.png'); }, 'image/png');
    };
    img.onerror = function () { toast('PNG \u5bfc\u51fa\u5931\u8d25'); };
    img.src = url;
  }

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function saveBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function toast(msg) {
    var t = document.getElementById('toast');
    if (t) {
      t.textContent = msg; t.style.display = '';
      setTimeout(function () { t.style.display = 'none'; }, 2500);
    } else alert(msg);
  }

  window._enhanceMermaid = enhanceAllMermaidBlocks;
  window._captureMermaidSources = captureMermaidSources;
})();
