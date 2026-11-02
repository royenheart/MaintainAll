# Reporting a plugin review

Use four buckets so a reader can act:

1. **Block**: install/runtime code with a concrete dangerous capability and no visible
   guard (install script, credential exfiltration, unauthenticated raw route, eval of
   untrusted input).
2. **Review**: a capability that may be legitimate but needs a guard/trace (network,
   filesystem, env, postMessage, broad inject).
3. **Not verified**: runtime behavior, auth reachability, transitive dependencies,
   remote destinations, browser behavior.
4. **Clean**: patterns scanned and not found; explicitly not a safety proof.

For each item: file:line, the observed code, why it matters, the smallest verification,
and the decision (block / safe with guard / allow). Do not paste secrets, cookies, or
raw prompts. Do not edit the plugin.
