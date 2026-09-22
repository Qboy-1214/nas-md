/**
 * draft_storage.js - Shared localStorage key contract for offline drafts.
 */
(function () {
  'use strict';

  var LEGACY_PREFIX = 'nasmd_draft_';
  var MODERN_PREFIX = 'nasmd_draft_v2_';

  function key(mountId, path) {
    return (
      MODERN_PREFIX + encodeURIComponent(String(mountId)) + ':' + encodeURIComponent(String(path))
    );
  }

  function legacyKey(path) {
    return LEGACY_PREFIX + path;
  }

  function parseKey(storageKey) {
    if (typeof storageKey !== 'string' || storageKey.indexOf(MODERN_PREFIX) !== 0) return null;
    var encoded = storageKey.slice(MODERN_PREFIX.length);
    var separator = encoded.indexOf(':');
    if (separator < 0) return null;
    try {
      return {
        mountId: decodeURIComponent(encoded.slice(0, separator)),
        path: decodeURIComponent(encoded.slice(separator + 1)),
      };
    } catch (_e) {
      return null;
    }
  }

  function parseLegacyKey(storageKey) {
    if (
      typeof storageKey !== 'string' ||
      storageKey.indexOf(LEGACY_PREFIX) !== 0 ||
      storageKey.indexOf(MODERN_PREFIX) === 0
    ) {
      return null;
    }
    return storageKey.slice(LEGACY_PREFIX.length);
  }

  function isDraftKey(storageKey) {
    return typeof storageKey === 'string' && storageKey.indexOf(LEGACY_PREFIX) === 0;
  }

  window.nasmdDraftStorage = Object.freeze({
    isDraftKey: isDraftKey,
    key: key,
    legacyKey: legacyKey,
    parseKey: parseKey,
    parseLegacyKey: parseLegacyKey,
  });
})();
