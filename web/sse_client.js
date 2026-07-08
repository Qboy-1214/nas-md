/**
 * sse_client.js - SSE client for real-time collaborative editing
 */
(function () {
  'use strict';

  var _client = null;

  function SSEClient() {
    this.es = null;
    this.identity = window.nasmdIdentity
      ? window.nasmdIdentity.get()
      : { id: 'unknown', name: 'Anonymous', color: '#3498db' };
    this.handlers = {};
    this._currentFile = null;
  }

  SSEClient.prototype.connect = function (mountId, path) {
    this.disconnect();
    var fileKey = mountId + ':' + encodeURIComponent(path);
    this._currentFile = mountId + ':' + path;
    var url =
      '/api/events?file=' +
      fileKey +
      '&name=' +
      encodeURIComponent(this.identity.name) +
      '&color=' +
      encodeURIComponent(this.identity.color);
    this.es = new EventSource(url);

    this.es.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        if (this.handlers[data.type]) {
          this.handlers[data.type](data);
        }
      } catch (_e) {
        // ignore malformed events
      }
    }.bind(this);

    this.es.onerror = function () {
      if (this.handlers['error']) {
        this.handlers['error']();
      }
    }.bind(this);
  };

  SSEClient.prototype.on = function (type, handler) {
    this.handlers[type] = handler;
  };

  SSEClient.prototype.disconnect = function () {
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
