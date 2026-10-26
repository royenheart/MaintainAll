# Native Application Streaming with Selkies

Read this after selecting native browser streaming in [Remote preview](remote-preview.md). The game runs in a server graphical session; the browser receives its picture and sound and returns input. Continue editing and launching the same engine project.

## Prepare one reusable session

1. Read the [desktop container documentation](https://github.com/selkies-project/selkies/blob/main/docs/components/desktop-image.md) for the selected release. Inspect the host's display/GPU devices and the engine's runtime requirements. Choose a supported renderer and encoder independently, then verify what actually runs.
2. Create a project-local streaming configuration with a pinned image digest, an explicit display size or client-resize policy, persistent application data, and a reproducible launch command. Mount the engine, project, and required data into a dedicated graphical session.
3. Launch the native project after that session is ready, for example `godot --path /workspace/game`. Use the session's display and audio server for graphical play, and headless execution for resource imports and nonvisual checks.
4. Select a transport supported by that release. WebSocket streaming can use one proxied web port; WebRTC requires its own connectivity checks. Serve through client-trusted HTTPS or an SSH-forwarded localhost endpoint, and configure session access before sharing the address.
5. Connect through the user's intended browser path. Capture a frame, exercise keyboard and pointer input, observe the resulting game state, and test audio when it matters to the next decision.

Read the engine log for the active renderer and the streaming log or GPU probe for the encoder. Record hardware and software paths as observed. Passing a GPU into a container and selecting a GPU are separate configuration steps; the visible device, driver libraries, display backend, and codec support must work together.

## Verify the complete feedback loop

| Check | Useful evidence |
|---|---|
| Actual native execution | Engine process/version and a frame from the graphical session |
| Remote interaction | A browser input changes movement, selection, or another observable state |
| Sound delivery | A known source reaches the client audio path; record separately whether a person checked listening quality |
| Atomic response | A short answer is saved with its question version, project/build identity, and tested profile |
| Reuse | Restart the configured session and reopen the same editable project through the same viewing route |

Native application output is written on the server. Mount its user-data directory persistently, provide a way to retrieve the response or artifact, and associate reactions with the source/build being played.

Keep a compact local record of the image digest, engine/version, project path, launch command, active renderer/encoder, resolution, transport, viewing route, and response location. Store credentials and host addresses in local deployment configuration. Reuse the session across creative rounds, extending capabilities only when the next question needs them.

Judge input feel and visual detail with the stream's capture, encoding, network, and decoding conditions in mind. Use target-device execution or native measurements when deciding the game's own performance. Continue through [progressive game creation](../../../references/game-creation.md) after the feedback path works.
