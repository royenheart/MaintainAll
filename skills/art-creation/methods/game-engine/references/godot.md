# Godot Execution and Browser Preview

Resolve the installed engine and query its version. Use matching official export templates. GDScript with the Compatibility renderer supports a shared native/Web project; choose another renderer or language when the intended target requires it. Godot 4 C# projects currently do not support Web export, and Web builds require WebAssembly and WebGL 2. Check the [official Web export documentation](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html) when choosing target features.

Choose the feedback route before detailed construction. [Remote preview](remote-preview.md) covers native application streaming and native client playback when Web export does not fit the game's requirements. The helper below supports native checks and Web/Linux exports; its HTTP server serves exported Web files.

Use the [project helper](../scripts/godot_project.py) from any directory. Replace `<method>` with this method's directory and keep each build in its own directory outside the source project:

```bash
python3 <method>/scripts/godot_project.py doctor
python3 <method>/scripts/godot_project.py init --output ./game
python3 <method>/scripts/godot_project.py check --project ./game
python3 <method>/scripts/godot_project.py export --project ./game --preset Web --output ./builds/web-v1
python3 <method>/scripts/godot_project.py serve --root ./builds/web-v1 --bind 127.0.0.1 --port 8792
```

Pass `--engine /path/to/godot` before the subcommand to select an installed binary. The helper's `--help` and subcommand help document arguments. The [starter scene](../templates/feel-lab/main.tscn), [game loop](../templates/feel-lab/main.gd), [player](../templates/feel-lab/player.gd), and [export presets](../templates/feel-lab/export_presets.cfg) remain ordinary editable Godot resources. The helper treats engine errors as failures even when the process exits with zero.

The starter uses a single-threaded Web export. The tested Godot 4.7.2 loader requires a secure context even for this export: use localhost through SSH forwarding or HTTPS for a remote host. The helper accepts `serve --cert <certificate> --key <private-key>`; keep keys outside the exported directory and use a certificate trusted by the client. Threaded Web builds also need cross-origin isolation; `--isolation-headers` supplies COOP/COEP.

On a remote server, bind the preview service to a reachable interface or forward its loopback port through SSH. Serve the exported build directory; the user's browser runs that game locally. Validate desktop GPU-specific features with a native build on the intended hardware.

Each export includes a file-hash manifest. Give each tested project revision a distinct `application/config/version` and retain its source revision and manifest with the feedback. The starter records the project version, question version, session/run, movement parameters, and answers. Reactions stay in memory until exported: Web execution downloads JSON to the client, while native execution writes JSON to Godot's user-data directory. Changing the profile resets the questions to match the new experiment.

Useful direct commands are `godot --headless --path <project> --import`, `godot --headless --path <project> --quit-after 30`, and `godot --headless --path <project> --export-release Web <absolute-build-path>/index.html`. The generated HTML is Godot's loader for the same project. See the [command-line reference](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
