# POPKEMON Character Theme Rationale

## Design Intent

POPKEMON is moving from a single clicker screen toward a character-based web app. The UI therefore needs a stable frame that can accept different Pokemon assets without feeling like a pasted image. The current direction treats each selected Pokemon as a user-owned zone: background light, cockpit panels, charge feedback, ranking lanes, and the logo accent all inherit the character palette.

## UX Rationale

- Recognition before instruction: users should know which character mode they are in without reading a label. A full-screen palette shift makes the selected Pokemon immediately legible.
- Ownership and return motivation: a character-colored arena makes the session feel like the user's chosen space, not a generic leaderboard. This supports future identity features such as Pokemon selection, trainer profile, and character-specific rankings.
- Reduced visual noise: the palette is limited to primary character color, secondary support color, and signal color. This prevents the earlier mixed neon look from competing with the tap target.
- Mobile-first focus: the center tap target stays stable while only the surrounding system changes. Users can switch characters without relearning where to tap, read score, or check ranking.
- Scalable leaderboard model: horizontal ranking cards imply expandable character lanes, which can later map to per-Pokemon boards without changing the main interaction model.

## Palette Logic

- Sneasel: purple and magenta for a sharp, nocturnal identity.
- Pikachu: yellow field with black structure and red signal accents, so the whole screen reads electric without becoming a flat yellow block.
- Charizard: orange heat with wing-teal support and cream signal, matching the asset while keeping contrast in the cockpit UI.

## Portfolio Framing

Case study narrative:

1. Problem: the Pokemon image and interface felt visually separate, so the product did not yet communicate future character selection.
2. Hypothesis: if the entire interface inherits the selected Pokemon palette, users will understand character ownership faster and feel stronger continuity between play, identity, and ranking.
3. Change: introduced character theme tokens and applied them to the background, logo mark, stats, arena, charge gauge, ranking lanes, and feedback effects.
4. Expected metrics: lower first-action hesitation, higher return_visit, higher ranking_view, and stronger name_set conversion after 10 pops.
5. Evidence to collect: before/after mobile screenshots, funnel deltas after sample threshold, and notes on whether users can identify the active character without reading the MON label.
