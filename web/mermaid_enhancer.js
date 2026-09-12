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
  var _fullscreenState = null;
  var _fullscreenListenersInstalled = false;
  var _trackingTimer = null;

  function removeLegacyMermaidUI() {
    var vditor = document.getElementById('vditor');
    if (!vditor) return;
    vditor.querySelectorAll('.mme-toolbar, .mme-code-area').forEach(function (element) {
      if (element.closest('.mme-global-overlay')) return;
      element.remove();
    });
    vditor.querySelectorAll('[data-mme-protected]').forEach(function (element) {
      if (!element.closest('.mme-global-overlay')) element.removeAttribute('data-mme-protected');
    });
  }

  function initOverlayLayer() {
    removeLegacyMermaidUI();
    installFullscreenListeners();
    var vditorContainer = document.querySelector('.vditor-content') || document.querySelector('.vditor');
    if (_overlayLayer) {
      if (!document.contains(_overlayLayer) && vditorContainer) {
        if (getComputedStyle(vditorContainer).position === 'static') {
          vditorContainer.style.position = 'relative';
        }
        vditorContainer.appendChild(_overlayLayer);
      }
      installUndoPatch(window._vditor && window._vditor.vditor);
      return _overlayLayer;
    }
    installUndoPatch(window._vditor && window._vditor.vditor);
    _overlayLayer = document.createElement('div');
    _overlayLayer.className = 'mme-global-overlay';
    _overlayLayer.style.position = 'absolute';
    _overlayLayer.style.top = '0';
    _overlayLayer.style.left = '0';
    _overlayLayer.style.width = '100%';
    _overlayLayer.style.height = '100%';
    _overlayLayer.style.pointerEvents = 'none'; // Let clicks pass through except on our UI
    _overlayLayer.style.zIndex = '1000';

    // Attach the overlay to the Vditor container so it scrolls with the editor.
    if (vditorContainer) {
      if (getComputedStyle(vditorContainer).position === 'static') {
        vditorContainer.style.position = 'relative';
      }
      vditorContainer.appendChild(_overlayLayer);
    }

    function loop() {
      updateOverlayPositions();
      _trackingTimer = requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);

    return _overlayLayer;
  }

  // Vditor IR snapshots include rendered Mermaid SVGs. Keep those snapshots
  // source-based, and make IR undo restore IR nodes instead of WYSIWYG nodes.
  function installUndoPatch(vditor) {
    if (!vditor || !vditor.undo || vditor.undo._mmePatched) return;
    var undo = vditor.undo;
    if (!undo.addCaret || !undo.renderDiff) return;
    undo._mmePatched = true;

    function withCanonicalMermaid(vditorArg, callback) {
      if (vditorArg.currentMode !== 'ir' || !vditorArg.ir || !vditorArg.ir.element) {
        return callback();
      }

      var saved = [];
      vditorArg.ir.element.querySelectorAll('.vditor-ir__preview').forEach(function (preview) {
        var rendered = preview.firstElementChild;
        if (!rendered || !rendered.classList.contains('language-mermaid')) return;

        var sourceMarker = preview.previousElementSibling;
        var source = sourceMarker && sourceMarker.querySelector('code');
        if (!source) return;

        var children = Array.prototype.slice.call(preview.childNodes);
        children.forEach(function (child) {
          preview.removeChild(child);
        });
        var sourceElement = document.createElement('code');
        sourceElement.className = 'language-mermaid';
        sourceElement.textContent = source.textContent || '';
        preview.appendChild(sourceElement);
        saved.push({ preview: preview, children: children, sourceElement: sourceElement });
      });

      try {
        return callback();
      } finally {
        saved.forEach(function (item) {
          if (item.sourceElement.parentNode === item.preview) {
            item.preview.removeChild(item.sourceElement);
          }
          item.children.forEach(function (child) {
            item.preview.appendChild(child);
          });
        });
      }
    }

    var originalAddCaret = undo.addCaret;
    undo.addCaret = function (vditorArg, insertWbr) {
      return withCanonicalMermaid(vditorArg, function () {
        return originalAddCaret.call(undo, vditorArg, insertWbr);
      });
    };

    var originalRenderDiff = undo.renderDiff;
    undo.renderDiff = function (patch, vditorArg, isRedo) {
      if (
        vditorArg.currentMode !== 'ir' ||
        !vditorArg.lute ||
        !vditorArg.lute.SpinVditorIRDOM
      ) {
        return originalRenderDiff.call(undo, patch, vditorArg, isRedo);
      }

      var lute = vditorArg.lute;
      var originalSpinVditorDOM = lute.SpinVditorDOM;
      var spinVditorIRDOM = lute.SpinVditorIRDOM;
      lute.SpinVditorDOM = function (html) {
        var rendered = spinVditorIRDOM.call(lute, html);
        var container = document.createElement('div');
        container.innerHTML = rendered;
        var preview = container.querySelector('.vditor-ir__preview');
        return preview ? preview.outerHTML : rendered;
      };
      try {
        return originalRenderDiff.call(undo, patch, vditorArg, isRedo);
      } finally {
        lute.SpinVditorDOM = originalSpinVditorDOM;
      }
    };

    if (vditor.currentMode === 'ir' && vditor.ir && vditor.ir.element && undo.ir) {
      undo.ir.lastText = withCanonicalMermaid(vditor, function () {
        return vditor.ir.element.innerHTML;
      });
    }
  }

  function updateOverlayPositions() {
    if (!_overlayLayer) return;
    var uis = _overlayLayer.querySelectorAll('.mme-overlay-item');
    uis.forEach(function (ui) {
      var blockId = ui.getAttribute('data-mme-id');
      var state = _blocks[blockId];
      if (!state || !state.targetEl || !document.contains(state.targetEl)) {
        if (state && state.fullscreenMode) clearFullscreenState(state);
        ui.remove();
        delete _blocks[blockId];
        return;
      }

      if (state.fullscreenMode) {
        ui.style.top = '0px';
        ui.style.left = '0px';
        ui.style.width = '100%';
        return;
      }

      var targetRect = state.targetEl.getBoundingClientRect();
      var layerRect = _overlayLayer.getBoundingClientRect();
      var toolbar = ui.querySelector('.mme-toolbar');
      var toolbarHeight = toolbar ? toolbar.offsetHeight : 38;
      ui.style.top = targetRect.top - layerRect.top - toolbarHeight + 'px';
      ui.style.left = targetRect.left - layerRect.left + 'px';
      ui.style.width = targetRect.width + 'px';
    });
  }

  function installFullscreenListeners() {
    if (_fullscreenListenersInstalled) return;
    _fullscreenListenersInstalled = true;
    document.addEventListener('fullscreenchange', handleNativeFullscreenChange);
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || !_fullscreenState || _fullscreenState.mode !== 'app') return;
      event.preventDefault();
      exitFullscreen(_fullscreenState.blockId);
    });
  }

  function fullscreenButtonFor(state) {
    return state.uiContainer
      ? state.uiContainer.querySelector('[data-action="toggleFullscreen"]')
      : null;
  }

  function updateFullscreenButton(state) {
    var button = fullscreenButtonFor(state);
    if (!button) return;
    var isFullscreen = !!state.fullscreenMode;
    var enterIcon = button.querySelector('.mme-icon-fullscreen');
    var exitIcon = button.querySelector('.mme-icon-exit-fullscreen');
    button.title = isFullscreen ? '退出全屏' : '全屏查看';
    button.setAttribute('aria-label', button.title);
    if (enterIcon) enterIcon.style.display = isFullscreen ? 'none' : '';
    if (exitIcon) exitIcon.style.display = isFullscreen ? '' : 'none';
  }

  function markFullscreenElements(state, active) {
    var target = state.targetEl;
    var container = state.uiContainer;
    if (active) {
      if (target) target.setAttribute('data-mme-fullscreen', 'true');
      if (container) container.setAttribute('data-mme-fullscreen', 'true');
      document.documentElement.classList.add('mme-fullscreen-active');
      document.body.classList.toggle('mme-app-fullscreen', state.fullscreenMode === 'app');
    } else {
      if (target) target.removeAttribute('data-mme-fullscreen');
      if (container) container.removeAttribute('data-mme-fullscreen');
    }
  }

  function clearFullscreenState(state) {
    if (!state) return;
    var isCurrent = _fullscreenState && _fullscreenState.state === state;
    state.fullscreenMode = null;
    markFullscreenElements(state, false);
    updateFullscreenButton(state);
    if (state.uiContainer) {
      state.uiContainer.style.top = '';
      state.uiContainer.style.left = '';
      state.uiContainer.style.width = '';
    }
    if (isCurrent) {
      document.documentElement.classList.remove('mme-fullscreen-active');
      document.body.classList.remove('mme-app-fullscreen');
      _fullscreenState = null;
    }
  }

  async function enterFullscreen(id) {
    var state = _blocks[id];
    if (!state || !state.targetEl || !state.uiContainer) return;
    if (_fullscreenState && _fullscreenState.state !== state) {
      await exitFullscreen(_fullscreenState.blockId);
    }

    _fullscreenState = { blockId: id, mode: null, state: state };
    var root = document.documentElement;
    if (root && typeof root.requestFullscreen === 'function') {
      try {
        await root.requestFullscreen();
        if (!_fullscreenState || _fullscreenState.state !== state) return;
        _fullscreenState.mode = 'native';
        state.fullscreenMode = 'native';
        markFullscreenElements(state, true);
        updateFullscreenButton(state);
        return;
      } catch (_error) {
        // Fall back to an application-level fullscreen view.
      }
    }

    if (!_fullscreenState || _fullscreenState.state !== state) return;
    _fullscreenState.mode = 'app';
    state.fullscreenMode = 'app';
    markFullscreenElements(state, true);
    updateFullscreenButton(state);
  }

  async function exitFullscreen(id) {
    if (!_fullscreenState || _fullscreenState.blockId !== id) return;
    var fullscreenState = _fullscreenState;
    try {
      if (
        fullscreenState.mode === 'native' &&
        document.fullscreenElement &&
        typeof document.exitFullscreen === 'function'
      ) {
        await document.exitFullscreen();
      }
    } catch (_error) {
      // Always clear the application state even if the browser API rejects.
    } finally {
      clearFullscreenState(fullscreenState.state);
    }
  }

  function handleNativeFullscreenChange() {
    if (
      _fullscreenState &&
      _fullscreenState.mode === 'native' &&
      !document.fullscreenElement
    ) {
      clearFullscreenState(_fullscreenState.state);
    }
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
    _blocks[blockId] = {
      zoom: 1,
      theme: 'light',
      mode: 'chart',
      sourceCode: sourceCode,
      targetEl: el,
      uiContainer: null,
      fullscreenMode: null,
    };

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

    _blocks[blockId].uiContainer = uiContainer;
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
      '<button class="mme-btn mme-fullscreen-control" data-action="toggleFullscreen" title="全屏查看" aria-label="全屏查看">' +
      '<svg class="mme-icon-fullscreen" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>' +
      '<svg class="mme-icon-exit-fullscreen" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>' +
      '</button>' +
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
      case 'toggleFullscreen':
        if (state.fullscreenMode) {
          exitFullscreen(id);
        } else {
          enterFullscreen(id);
        }
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
