# MinecraftToBlender v1.1.2

## Bedrock export hotfix
- Fix the hanging-sign `attached_bit` model expression so it parses with the pinned MiEx experimental-34 expression engine. v1.1.1 used a nested ternary equality expression that could abort resource-pack initialization, prevent Minecraft materials from being generated, and cause secondary missing frame/glow-frame blockstate errors.
- Keep the Bedrock chain attachment handling without introducing a new option or changing saved worlds.
- Add a Windows CI regression that downloads and SHA-256-verifies the exact MiEx.jar used by the EXE, then compiles and executes model-expression parsing against MiEx's own Java implementation. Static JSON checks alone had missed this issue.

## More accurate Java memory reporting
- Stop treating a small Java launcher process's initial working set (often around 10 MiB) as the entire MiEx JVM's memory usage.
- Prefer real matching Java child processes by process ancestry and `MiEx.jar` command line, rather than guessing from unrelated Java processes.
- Show the JVM's **private committed memory**, **physical resident working set**, and process ID with explicit units. Measurements below the reliable threshold are labeled unavailable.
- Continue live memory samples while a Java launcher has exited but the child JVM still holds the captured output streams open. Export behavior and the heap limit are otherwise unchanged.

## Validation and safety
- Existing export and Blender settings stay the same. The original world and previous complete exports remain untouched on errors.
- This is a bugfix release; no old MinecraftToBlender version migrations, optional toggles, or separate user-run scripts were added.
- CI validates code and Windows EXE; complete visual fidelity in a real user Bedrock world requires additional testing.
