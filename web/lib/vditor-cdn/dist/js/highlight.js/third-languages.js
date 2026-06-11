// third-languages.js placeholder
// Vditor loads this file for additional highlight.js language support
// Original source: https://cdnjs.cloudflare.com/ajax/libs/vditor/3.10.7/js/highlight.js/third-languages.js
hljs.registerLanguage("yul",(()=>{"use strict";return e=>{return{keywords:{keyword:"assembly let function if switch case default for leave break continue"},contains:[e.C_LINE_COMMENT_MODE,e.C_BLOCK_COMMENT_MODE]}}})());
hljs.registerLanguage("solidity",(()=>{"use strict";return e=>{return{aliases:["sol"],keywords:{keyword:"pragma solidity contract function modifier event import from as using"},contains:[e.C_LINE_COMMENT_MODE,e.C_BLOCK_COMMENT_MODE,e.APOS_STRING_MODE,e.QUOTE_STRING_MODE]}}})());
hljs.registerLanguage("abap",(()=>{"use strict";return e=>{return{case_insensitive:!0,aliases:["sap-abap","abap"],keywords:{keyword:"DATA BEGIN END FORM ENDFORM PERFORM USING CHANGING TYPE LIKE"},contains:[e.APOS_STRING_MODE,e.NUMBER_MODE]}}})());
hljs.registerLanguage("hlsl",(()=>{"use strict";return e=>{return{keywords:{keyword:"float half int uint bool void struct cbuffer tbuffer register sampler texture if else for while do return break continue"},contains:[e.C_LINE_COMMENT_MODE,e.C_BLOCK_COMMENT_MODE,e.NUMBER_MODE]}}})());
