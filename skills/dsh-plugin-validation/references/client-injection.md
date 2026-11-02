# Client injection

The Web client is JavaScript in the user's browser. Host React escaping helps only
when values flow through React text nodes; `innerHTML`, `dangerouslySetInnerHTML`,
`document.write`, `insertAdjacentHTML`, and `eval`/`new Function` bypass it.

Review:

- all HTML sinks; trace values to model output, tool output, session titles, file
  names, or remote responses;
- `postMessage` handlers: validate `event.origin` and use an explicit `targetOrigin`;
- remote script/module URLs, dynamic `import()` of untrusted URLs, and CDN fallbacks;
- slot/command registration that can override host UI;
- locale strings loaded from untrusted files;
- client bundle source and `files` packaging: a linked checkout can hide a missing
  client artifact.

Prefer React nodes and a fixed allowlist/sanitizer. Do not claim sanitization from a
regex; confirm with a browser test in a throwaway profile.
