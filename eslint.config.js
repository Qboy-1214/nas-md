import js from "@eslint/js";
import prettier from "eslint-plugin-prettier";
import prettierConfig from "eslint-config-prettier";

export default [
  js.configs.recommended,
  prettierConfig,
  {
    files: ["web/**/*.js"],
    plugins: {
      prettier,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        // Browser globals
        window: "readonly",
        document: "readonly",
        console: "readonly",
        fetch: "readonly",
        localStorage: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        HTMLElement: "readonly",
        Event: "readonly",
        FormData: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        DOMParser: "readonly",
        TreeWalker: "readonly",
        NodeFilter: "readonly",
        Range: "readonly",
        Selection: "readonly",
        Node: "readonly",
        MutationObserver: "readonly",
        getComputedStyle: "readonly",
        navigator: "readonly",
        history: "readonly",
        location: "readonly",
        alert: "readonly",
        prompt: "readonly",
        confirm: "readonly",
        // Cross-file functions (defined in app.js, referenced from editor.js)
        onEditorInput: "readonly",
        _findHeadingAboveCursor: "readonly",
        // Third-party libraries
        Alpine: "readonly",
        Vditor: "readonly",
        d3: "readonly",
        // Custom globals (defined across JS files, used via HTML onclick)
        state: "writable",
        $: "readonly",
        $$: "readonly",
        API: "writable",
        _apiBase: "readonly",
        initEditor: "readonly",
        setFileInfo: "readonly",
        clearTreeCache: "readonly",
        renderFileTree: "readonly",
        indexedDB: "readonly",
      },
    },
    rules: {
      "prettier/prettier": "error",
      "no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern:
            "^(openFile|saveFile|showNewFile|hideNewFile|confirmNewFile|toggleSidebar|toggleDarkMode|toggleAutoSave|toggleBacklinks|toggleMount|toggleDir|toggleMountPublic|removeMount|navigateHome|showGraph|showDashboard|doSearch|setEditorMode|markDirty|markClean|markSaved|chooseDirectory|onDirPicked|loadMounts|loadTree|getTreeCached|clearTreeCache|findMountForPath|getRelativePath|getMountPath|restoreCursorPosition|isDirty|getCurrentFileInfo|setFileInfo|createItem|renderSidebar|loadLocalTree|getLocalDirHandle|_treeHasPath|refreshTree|startSidebarRefresh|stopSidebarRefresh|startSyncPolling|stopSyncPolling|performSync|collectFileMtimes|saveToLocalStorage|loadFromLocalStorage|clearLocalStorage|loadRecentFiles|collectFiles|renderRecentFiles|formatTime|renderGraph|updateSyncIndicator|startDirtyCheck|scheduleAutoSave|_scrollToKeyword|readLocalDir|readLocalFile|getLocalFileHandle|writeLocalFile|mountLocalDirectory|showPage|showToast|findMountForPath|idbOpen|idbPut|idbGet|idbDelete|idbGetAllKeys|setupDragDrop|showMoveCopyDialog|moveServerItem|moveLocalItem|copyLocalDir|crossMountServer|crossMountLocal|showRenameModal|renameServerItem|renameLocalItem|localToServer|serverToLocal|onEditorInput|_dragData|_dragDropSetup|_refreshTreeBusy|deleteCurrentFile)$",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "no-undef": "error",
      "no-empty": "off",
      "no-redeclare": "off",
      "no-useless-escape": "warn",
    },
  },
  {
    ignores: ["web/lib/**", "node_modules/**", "tests/**"],
  },
];
