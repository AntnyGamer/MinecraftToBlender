# MinecraftToBlender v1.0.3

- Add a clean, minimalist Minecraft-to-Blender application logo to the Windows executable, the main window, the world picker, and the GitHub README. A multiresolution icon remains sharp at common Windows display sizes.
- Fix the Windows Explorer process handle not being released after opening the output folder.
- Name Blender projects after the selected world (or chosen Export Name), such as `Night_Blades_Survival.blend` and `Night_Blades_Survival_2.blend` for subsequent imports. Existing projects remain intact.
- Display the same new logo in the main app sidebar instead of the old blue placeholder; retain the placeholder only if Windows cannot draw the icon.
- Keep the SVG branding source out of bundled conversion helpers, avoiding unnecessary extraction on each workspace setup.

- Skip the redundant proxy-variant USD geometry scan when render terrain is already valid. If render contains no usable geometry, try proxy instead of aborting early.

**Note:** World export and USD-to-Blender fidelity still depend on the selected world and MiEx. Verify the resulting scene visually.
