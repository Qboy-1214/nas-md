/**
 * sse_client.js - SSE client for real-time collaborative editing
 */
(function () {
  'use strict';

  var HEARTBEAT_TIMEOUT_MS = 45000; // 45 seconds

  function SSEClient() {
    this.es = null;
    this.identity = window.nasmdIdentity
      ? window.nasmdIdentity.get()
      : { id: 'unknown', name: 'Anonymous', color: '#3498db' };
    this.handlers = {};
    this._currentMountId = null;
    this._currentPath = null;
    this._heartbeatTimer = null;

    // Auto-reconnect when tab becomes active or network comes online
    var self = this;
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible' && self._currentMountId && self._currentPath) {
        self._checkAndReconnect();
      }
    });
    window.addEventListener('online', function () {
      if (self._currentMountId && self._currentPath) {
        self._checkAndReconnect();
      }
    });
  }

  SSEClient.prototype._resetHeartbeat = function () {
    if (this._heartbeatTimer) {
      clearTimeout(this._heartbeatTimer);
    }
    var self = this;
    this._heartbeatTimer = setTimeout(function () {
      console.warn('[SSE] Heartbeat timed out, reconnecting...');
      self._checkAndReconnect();
    }, HEARTBEAT_TIMEOUT_MS);
  };

  SSEClient.prototype._checkAndReconnect = function () {
    if (this._currentMountId && this._currentPath) {
      this.connect(this._currentMountId, this._currentPath);
    }
  };

  SSEClient.prototype.connect = function (mountId, path) {
    this.disconnect();
    this._currentMountId = mountId;
    this._currentPath = path;

    var fileKey = mountId + ':' + encodeURIComponent(path);
    var url =
      '/api/events?file=' +
      fileKey +
      '&name=' +
      encodeURIComponent(this.identity.name) +
      '&color=' +
      encodeURIComponent(this.identity.color);

    this.es = new EventSource(url);
    this._resetHeartbeat();

    var self = this;
    this.es.onmessage = function (event) {
      self._resetHeartbeat();
      try {
        var data = JSON.parse(event.data);
        if (self.handlers[data.type]) {
          self.handlers[data.type](data);
        }
      } catch (_e) {
        // ignore malformed events
      }
    };

    this.es.onerror = function () {
      if (self.handlers['error']) {
        self.handlers['error']();
      }
    };
  };

  SSEClient.prototype.on = function (type, handler) {
    this.handlers[type] = handler;
  };

  SSEClient.prototype.disconnect = function () {
    if (this._heartbeatTimer) {
      clearTimeout(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
    if (this.es) {
      this.es.close();
      this.es = null;
    }
  };

  SSEClient.prototype.switchFile = function (mountId, path) {
    this.connect(mountId, path);
  };

  window.nasmdSSE = new SSEClient();
})();
