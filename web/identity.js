/**
 * identity.js - Anonymous identity management for collaborative editing
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'nasmd_identity';

  var ADJECTIVES = ['Swift', 'Calm', 'Bold', 'Keen', 'Wise', 'Bright', 'Silent', 'Wild'];
  var ANIMALS = ['Fox', 'Owl', 'Cat', 'Bear', 'Wolf', 'Raven', 'Crane', 'Deer'];
  var COLORS = [
    '#e74c3c',
    '#3498db',
    '#2ecc71',
    '#f39c12',
    '#9b59b6',
    '#1abc9c',
    '#e67e22',
    '#34495e',
  ];

  function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function parseUserAgent() {
    var ua = navigator.userAgent;
    var os = 'Unknown OS';
    var browser = 'Unknown Browser';

    if (ua.includes('Windows')) {
      os = 'Windows';
    } else if (ua.includes('Mac OS')) {
      os = 'macOS';
    } else if (ua.includes('Linux') && !ua.includes('Android')) {
      os = 'Linux';
    } else if (ua.includes('Android')) {
      os = 'Android';
    } else if (ua.includes('iPhone') || ua.includes('iPad') || ua.includes('iOS')) {
      os = 'iOS';
    }

    if (ua.includes('Edg/')) {
      browser = 'Edge';
    } else if (ua.includes('Chrome/') && !ua.includes('Edg/')) {
      browser = 'Chrome';
    } else if (ua.includes('Safari/') && !ua.includes('Chrome/')) {
      browser = 'Safari';
    } else if (ua.includes('Firefox/')) {
      browser = 'Firefox';
    } else if (ua.includes('Opera') || ua.includes('OPR/')) {
      browser = 'Opera';
    }

    return { os: os, browser: browser };
  }

  function generateIdentity() {
    var name = pick(ADJECTIVES) + pick(ANIMALS) + Math.floor(Math.random() * 100);
    var color = pick(COLORS);
    var id = crypto.randomUUID();
    var clientInfo = parseUserAgent();
    return { id: id, name: name, color: color, os: clientInfo.os, browser: clientInfo.browser };
  }

  function getIdentity() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        var parsed = JSON.parse(stored);
        if (!parsed.os || !parsed.browser) {
          var clientInfo = parseUserAgent();
          parsed.os = clientInfo.os;
          parsed.browser = clientInfo.browser;
          localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
        }
        return parsed;
      }
    } catch (_e) {
      // ignore
    }
    var id = generateIdentity();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(id));
    } catch (_e) {
      // ignore quota errors
    }
    return id;
  }

  window.nasmdIdentity = { get: getIdentity };
})();
