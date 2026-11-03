# MinecraftToBlender v1.0.5

- Fix Blender opening an unnecessary Command Prompt/console window after an automatic project launch or when using **Open project**.
- Launch the interactive Blender application using Windows `CREATE_NO_WINDOW`, which suppresses the console without requesting that Blender's main GUI be hidden.
- Retain the existing auto-open On/Off setting, completed-project validation, manual Open project action, and all v1.0.4 export and re-export fixes.

**Note:** This fixes the application's Blender launch method. The complete workflow still requires an installed Blender and a successful Minecraft world conversion.