# Appearance studies

Appearance is a small local preference under **Settings → Appearance**. It does not change layouts, executor settings, project data or model usage. The original dark palette remains the default and can be restored.

| Study | Palette | Visual grammar |
| --- | --- | --- |
| Graphite · Minimal | Cool white, mist gray, graphite | Fine dividers, generous surfaces, quiet shadows, neutral actions |
| Construct · Burgundy | Warm paper, burgundy, charcoal | Crisp corners, a strong horizontal rule, offset geometry inside the preview |
| Obsidian · Metal | Near-black, steel gray, restrained crimson | Layered panels, narrow metallic highlights, subtle CSS gradients |

Preview illustrations are original HTML/CSS compositions. No external fonts, raster textures, branded logos, continuous animation or visual-effect libraries are loaded. Decorative geometry stays out of task and chat content. Status dots, explicit text, focus outlines and error/success colors remain semantic across palettes.

`static/themes.css` maps shared workspace surfaces, forms, drawers, chat panels, agent settings and state colors onto semantic tokens. `static/appearance.js` applies a validated theme ID before first paint and saves only `agentboard.theme` in browser-local storage. If storage is unavailable, switching still works for the current page. Theme selection never makes a network request or re-renders user forms. Keyboard users can move through native radio controls; reduced-motion and forced-color preferences are respected.

When adding a new panel, use existing tokens rather than a fixed dark background. Check both light palettes and the metal palette with a long task title, an open form, a chat conversation and an error state. Keep public-facing release notes short: coordination remains the project's primary purpose.
