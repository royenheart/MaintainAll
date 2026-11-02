# Capability review

Ask what the plugin can do, not only whether it contains a bad string.

- Host `inject`: which services can it read or replace? Does it need them for the
  documented feature?
- Hooks/events: does it intercept every session/tool/message, or only its own?
- Client slots/commands/keybindings: can it replace host UI or capture input?
- Filesystem: does it need the workspace, `$DSH_HOME`, the user's home, or a credential
  path? Trace the path source.
- Network: which destinations, what payload, and is TLS/origin checked?
- Subprocess: argv, shell, cwd, env, cancellation, stdout/stderr ownership.
- Patches: does it monkeypatch the host, edit `node_modules`, or modify the profile
  patch? A bundle patch is composition; a source monkeypatch is a host change.
- Preset/agent: does it change prompts, tools, permissions, or model routing beyond
  its documented scope?

Report the minimum capability the feature needs and the extra capability observed.
