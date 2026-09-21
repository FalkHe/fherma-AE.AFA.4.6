# Goblin Pub — Design System

A dark-only interface system for a Dungeons & Dragons **Dungeon Master agent**: a web app where a party talks to an AI DM in a chat log, watches dice resolve, and keeps character sheets on a rail beside the conversation.

The room this system imagines is a goblin pub buried deep in an Irish wood — low ceilings, wet green dark outside, one amber lantern doing all the work inside. Everything is warm, brown-green and softly rounded; nothing is cut square.

## Sources

No codebase, Figma file, deck or brand assets were supplied. This system was authored from the written brief:

> "Design system for a DND Dungeon Master Agent Web application. Use warm natural and dark colour (darkmode always). Green/brown. Inspired by a fantasy Goblin Pub hidden deeply in the Irish woods. Round natural edges. Decorated by plants. We need basic UI features like cards, buttons, icons, text form. Basically a chat view and a player stat card. Maybe some scene images."

Everything here is therefore a proposal, not a recreation. Where a real asset would normally live (logo, scene art, portraits) the system renders an honest placeholder rather than inventing one.

## Products

One product today: **the Goblin Pub web app** (`ui_kits/goblin-pub-app/`) — campaign list, live session view (chat + party rail), and character sheet.

---

## Content fundamentals

Two voices share the screen and they must never blur.

**The DM agent** narrates in tight, sensory present tense, set in the display serif. It describes what is there and stops; it does not ask "what would you like to do?" every turn, and it never breaks character to explain itself.

> "The door gives with a wet crack. Inside, three goblins are arguing over a barrel of something that used to be ale."

**The interface** speaks plainly in the sans, second person, sentence case, no exclamation marks.

> "Roll dice for the party" · "Your party sees this." · "The log is saved to your campaign either way."

Rules:

- **You / your** for the player. The agent refers to itself as "the Dungeon Master", never "I, your AI assistant".
- **Sentence case** everywhere except small-caps labels (`PARTY · ROUND 3`), which are all caps with 0.14em tracking.
- **No emoji, ever** — not in copy, not in the UI. Mood is carried by type, colour and the icon set.
- **Mechanics are terse and mono**: `Persuasion check · DC 14`, `1d20+7 = 13 + 7`, `HP 24/32`.
- **Buttons are verbs with a bit of table talk**: "Light the lantern", "Roll initiative", "End session" — flavour is allowed on primary actions, never in destructive confirmations, which stay literal.
- **Errors are matter-of-fact**, no apology and no character voice: "A name is required."
- Placeholders invite play: "What do you do?"

## Visual foundations

**Colour.** Five ramps, all defined in `tokens/colors.css`. *Loam* (#0B0E09 → #5F6B4A) is the green-black the app sits on — four surface steps: app, sunken, card, raised. *Bark* is the brown timber used for secondary buttons, asides and portrait frames. *Lantern* amber (#E8A94A) is the single primary accent: one primary button per view, plus focus rings and the DM's warm wash. *Moss* green is the secondary accent — success, healthy HP, moss-outline buttons. *Ember* red is damage and danger; *Fen* teal is magic and info, used sparingly. Text is *parchment*: four ink levels, all at or above 4.5:1 on card surfaces.

**Type.** Alegreya (display serif) for narration, headings and numbers on stat cards. Alegreya Sans for all interface copy. Alegreya SC for small-caps labels. JetBrains Mono for dice notation, HP values and timestamps. The scale runs 44 / 32 / 24 / 19 / 18 / 16 / 14 / 12.5.

**Spacing.** A 4px-based scale with a tight low end (2, 4, 8, 12, 16, 20, 24, 32, 40, 56, 72, 96). Card padding is 20px, standard stack gap 16px, tight groups 8px. The chat column is capped at 760px; the party rail is a fixed 300px; the icon rail is 68px.

**Backgrounds.** No photography in chrome, no full-bleed gradients as decoration. Depth comes from three washes: `--wash-lantern` (a radial amber pool bleeding down from the top of a panel, as if from a hanging lamp), `--wash-moss` (a cool green pool at the top-left of the session canvas, the woods pressing in), and `--grain`, a nearly invisible diagonal hairline texture over imagery. Scene plates get `--scrim-bottom`, a protection gradient so captions stay legible over art.

**Corners.** Radii are large: 6 / 10 / 14 / 20 / 28 / pill. Big panels use `--radius-organic` (22px 16px 24px 18px) — deliberately uneven, so containers read as hand-cut wood rather than CSS boxes. Buttons and badges are full pills.

**Cards.** One-pixel hairline border (`rgba(226,214,186,.14)`), organic radius, `--shadow-md` (a deep warm drop plus a 6%-white inset top edge that reads as light catching a lip). Four tones: default loam, raised, timber brown, and sunken (an inset well used for logs and lists).

**Shadows.** Deep and warm rather than neutral: `0 6px 18px -6px rgba(0,0,0,.62)`. Two glows exist — `--glow-lantern` marks the live element (focused composer, primary hover, the character whose turn it is) and `--glow-moss` marks a checked control. Glow is meaning, never decoration.

**Animation.** Fast and soft: 150ms for hover/focus colour, 220ms for toggles, 400ms for HP drain and dialogs, all on `--ease-out-soft` (cubic-bezier(.16,.84,.44,1)). No bounce, no spring, no slide-in-from-nowhere. The one ambient loop in the product is the candle flicker on the typing indicator (1.4s, staggered 0.18s). Everything collapses to 0ms under `prefers-reduced-motion`.

**States.** Hover *lightens*: primary brightens 7% and picks up the lantern glow; ghost gains a 6%-white film; timber goes one step lighter. Press is `translateY(1px) scale(.99)` with no colour change. Focus is a 2px lantern-300 outline at 2px offset; inside fields it is a 1px amber border plus a 3px 16%-amber halo. Disabled is 42% opacity and `not-allowed` — never a grey repaint.

**Transparency and blur.** Blur appears exactly once: 6px behind the modal scrim (`rgba(8,10,7,.72)`). Alpha is otherwise reserved for borders, quiet badge fills (14–16%) and washes. Text is never alpha-muted; it steps down the parchment ramp instead.

**Layout rules.** The icon rail and top bar are fixed; the log scrolls and pins to the bottom on new messages; the composer is docked and grows with content; the party rail scrolls independently. Modals are centred, max 520px.

**Imagery.** Warm, low-key, candle-lit — amber highlights against green-black shadow, with visible grain. Cool blues only for magic. **No scene art ships with this system**; `SceneImage` renders a captioned placeholder until real artwork is provided.

## Iconography

**Lucide** (outline, 2px stroke, 24px grid) served from `unpkg.com/lucide-static`, masked to `currentColor` by the `Icon` component. **This is a substitution** — no icon set was supplied with the brief. Swap the CDN base in `components/core/Icon.jsx` if you adopt a different set.

- Sizes: 12 in badges, 15–16 in dense controls, 17–18 default, 20–22 in headers.
- Icons are always monochrome and inherit text colour; tint only via `color="var(--accent)"` when the icon carries status.
- No emoji. No unicode-glyph icons. No hand-drawn one-off SVGs.
- House vocabulary: `dices` (rolls), `flame` (the DM / lantern), `swords` (combat), `shield` (AC), `heart` (HP), `users` (party), `scroll-text` (notes), `book-open` (campaign), `map`, `backpack` (inventory), `beer` (tavern/session), `sparkles` / `wand-sparkles` (magic), `footprints` (initiative), `feather` (naming), `send`, `plus`, `settings`, `x`, `chevron-down`.

**No logo exists.** The brand name is set in Alegreya SC wherever a mark would go (see the Wordmark card and `thumbnail.html`). Do not draw one.

## Intentional additions

- **Icon** — a wrapper around the Lucide set so every glyph inherits colour and sizing consistently.
- **Field** — label/hint/error wrapper; without it every form control would re-implement its own label.

---

## Index

| Path | What it is |
| --- | --- |
| `styles.css` | The single entry point consumers link. Imports only. |
| `tokens/` | `fonts.css`, `colors.css`, `typography.css`, `spacing.css`, `surfaces.css`, `motion.css`, `base.css`. |
| `guidelines/` | 17 specimen cards: colour ramps, type, spacing, radii, elevation, washes, motion, wordmark. |
| `components/` | React primitives, grouped by concern. Each has `.jsx`, `.d.ts`, `.prompt.md`; each folder has one card. |
| `ui_kits/goblin-pub-app/` | Click-through recreation of the app. See its README. |
| `mui/` | MUI theme options (`goblinPubTheme.js`) + integration notes for React apps built on @mui/material. |
| `templates/session-view/` | Starting-point template: the session view, ready to copy into a consuming project. |
| `SKILL.md` | Agent-skill entry point. |

### Components

**core/** — `Button`, `IconButton`, `Icon`, `Card`, `Badge`, `Tag`, `Divider`, `Dialog`

**forms/** — `Field`, `Input`, `Textarea`, `Select`, `Checkbox`, `Switch`

**chat/** — `ChatMessage`, `ChatComposer`, `TypingIndicator`, `DiceRoll`

**game/** — `PlayerStatCard`, `AbilityScore`, `ResourceBar`, `SceneImage`

### MUI

The system ships a MUI theme: `mui/goblinPubTheme.js` exports `goblinPubThemeOptions` (pass to `createTheme`) and `goblinPubTokens` (the full ramps, also mounted at `theme.palette.goblin`). Palette, typography, spacing (4px base), shadows, transitions and ~25 component overrides are mapped from the same tokens. See `mui/README.md`. The React components in `components/` are MUI-independent and can be mixed with MUI components in the same app.

### Known gaps

- **Fonts are Google Fonts substitutions** (Alegreya / Alegreya Sans / JetBrains Mono) loaded over the network, not licensed brand binaries. Supply real files and they can be self-hosted as `@font-face`.
- **Icons are a Lucide substitution** loaded from a CDN.
- **No logo, no scene art, no character portraits.** Placeholders everywhere they belong.
- Plant decoration is currently expressed through colour and the organic radius only — no botanical illustration assets exist to place in corners and dividers.
