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

  function generateIdentity() {
    var name = pick(ADJECTIVES) + pick(ANIMALS) + Math.floor(Math.random() * 100);
    var color = pick(COLORS);
    var id = crypto.randomUUID();
    return { id: id, name: name, color: color };
  }

  function getIdentity() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return JSON.parse(stored);
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
