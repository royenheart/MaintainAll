# Native and Remote Game Preview

Choose the game's runtime features first, then a feedback path that supports them. Browser access can mean local Web execution or streamed native execution. Preserve the intended renderer, language, dependencies and input behavior when choosing between them.

| Route | Where the game runs | Browser or client role | Useful when |
|---|---|---|---|
| Engine Web export | User device | Loads the Web engine and project, then runs and renders locally | The project supports the browser target and link-based distribution is useful |
| Native application streaming | Server graphical session | Receives encoded video/audio and sends input | The user wants browser access to a game using native runtime capabilities |
| Native build on user device | User device | Opens a desktop build or the project in its engine | Target-device behavior or direct input timing is the question |

Godot's [Web export documentation](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html) currently requires WebAssembly/WebGL 2 and the Compatibility renderer, excludes Godot 4 C# Web export, and describes additional platform limitations. Native extensions need a suitable Web build and supported dependencies. Choose native execution when those conditions conflict with the project.

## Select a streaming backend when needed

| Option | Read | Role |
|---|---|---|
| Selkies | [Session setup and verification](selkies.md) | Linux application/desktop streaming to a browser, hardware or software encoding, WebSocket transport with optional WebRTC |
| noVNC with a VNC server | [Official overview](https://novnc.com/info.html) | Browser desktop access for editor inspection and suitable interactive tasks; verify the actual motion/audio requirements |
| Sunshine with Moonlight | [Official documentation](https://docs.lizardbyte.dev/projects/sunshine/latest/) | Native game-streaming host/client route; Sunshine's configuration web UI is separate from a playable browser client |

Use a project-specific graphical session for reproducible launches. Check the selected renderer, display/capture path, encoding support and input/audio route. Launch the native project in that session, such as `godot --path <project>`, or run its native build. Use headless mode for import and nonvisual checks; graphical play needs a rendering session. Streaming the native project does not require a Web game build.

Validate the actual viewing path with a small scene: start, receive a frame, send input, observe the state change, and exercise audio or controls relevant to the question. Retain the launch command, source/build identity, tested resolution, client route and feedback channel. Reuse that session or reproducible configuration for later iterations.

Streaming adds capture, encoding, network and decoding time to the input-feedback path, and compression can affect visible detail. Record those conditions when judging feel or visual quality. Use native measurements or target-device tests to answer questions about the game's own timing and performance.

The [Godot helper](godot.md) initializes, checks and exports projects and serves Web files. Configure the selected streaming backend alongside the project, then reuse its working session for subsequent experiments.
