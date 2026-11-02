# Threat model

A dsh plugin is not a passive package. Host plugins run inside the host process with
the user's permissions; client plugins run in the browser with the page's origin and
session context. A third-party plugin can therefore:

- execute install-time code through package lifecycle scripts or a git `prepare`;
- read or send credentials, cookies, environment variables, `$DSH_HOME`, workspace
  files, and session data;
- expose network routes or WebSockets without the host's auth gate;
- inject markup/JavaScript into the Web client;
- intercept or replace host services, hooks, slots, tools, or events;
- modify `node_modules`, the host package, or the profile composition.

Trust boundaries: registry/package source, install scripts, host process, profile,
workspace, browser origin, model provider, and the user's credentials. Each boundary
needs its own evidence. A clean static scan does not prove runtime safety; a running
plugin can fetch a payload later.

Report the boundary you actually verified and the one you did not. Do not execute
untrusted install scripts on the user's host to find out.
