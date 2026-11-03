# MinecraftToBlender v1.0.3

- Add a clean, minimalist Minecraft-to-Blender application logo to the Windows executable, the main window, the world picker, and the GitHub README. A multiresolution icon remains sharp at common Windows display sizes.
- Fix the Windows Explorer process handle not being released after opening the output folder.
- Allow the last available numbered Blender output (`_REPAIRED_100.blend`) instead of reporting a filename collision prematurely.
- Match the Windows title-bar dark appearance to the app's existing dark interface.
- Keep the SVG branding source out of bundled conversion helpers, avoiding unnecessary extraction on each workspace setup.

**Note:** World export and USD-to-Blender fidelity still depend on the selected world and MiEx. Verify the resulting scene visually.
