# Motorcycle Model Names

Reference for naming, identifying and grouping motorcycle models.

## Core statement

**The model name is not the identity.** Three independent levels must be kept apart in the data model:

| Level | Example | Rate of change |
|---|---|---|
| Marketing name | "Yamaha MT-07" | rarely, sometimes stable for 10+ years |
| Technical generation (type code) | RM04 → RM17/18 → RM33/34 → RM48–51 | every 3–4 years |
| Model year | 2014 … 2026 | yearly (colours, packages, price) |

The MT-07 has been called "MT-07" continuously since 2014, yet it has already run through six or more type codes. Using `name + year` as a key lumps technically incompatible machines together.

## Naming patterns

1. **Name stays, generation changes silently** – Yamaha MT-07/MT-09, Kawasaki Z900, Ducati Monster, Triumph Bonneville, Honda CBR1000RR (SC28 → SC33 → SC44 → SC50 → SC57 → SC59 → SC77 → SC82)
2. **Displacement in the name → name changes when the engine changes** – BMW R 1200 GS → R 1250 GS → R 1300 GS; KTM 1290 → 1390 Super Duke R; Honda CRF1000L → CRF1100L
3. **Name + suffix for variants** – SP, S, R, RS, RR, GT, Adventure, Rally, Pro, Performance, Triple Black. These are variants of the same generation, not models of their own.
4. **Name recycling after decades** – BMW R 18 (2020 vs. 1936), Honda CB750 Hornet (2023) vs. CB750 Four (1969). This is why `name + year` is not enough; `name + generation` is required.

### Pitfalls

- **Displacement in the name ≠ actual displacement**: MT-09 = 890 cc, KTM 1290 = 1301 cc, BMW F 900 = 895 cc. Never derive it from the name.
- **Spellings diverge**: BMW "R 1300 GS" (with spaces), Honda "CB750 Hornet", Ducati "Multistrada V4 S". Users type "R1300GS". → An alias/synonym table is mandatory.
- **Harley-Davidson** uses its own model codes (FLFBS = Fat Boy 114) in parallel with the name.

## Data model

```
Manufacturer                       BMW Motorrad
 └ Buildingline (model family)     GS  /  Honda: CBR  /  Yamaha: MT
    └ Model                        "R 1300 GS"        ← search unit
       └ Generation (type code)    K81, 2023–         ← unit of truth
          └ Variant (trim)         Base | Adventure | Triple Black
             └ ModelYear           2024 | 2025 | 2026  ← colours, packages, price
```

Stable slug: `bmw/r-1300-gs/k81/adventure`

A model is identified by **manufacturer, buildingline, variant and year range**. The generation/type code stays internal and is only used where technical compatibility matters.

### When to create a new `Generation`

| Trigger | New generation? |
|---|---|
| New manufacturer type code (K.., SC.., RM.., ZR..) | yes |
| New frame or engine | yes |
| New emission standard with re-homologation | yes |
| Colours, packages, price only | no → new ModelYear |

### Field assignment

Displacement, power (kW **and** hp), licence class and emission standard belong on `Generation`/`Variant`, never on `Model`. Store segment, vehicle class, licence class and emission standard as enums, not as strings.

## Naming formula for humans

```
{Manufacturer} {Model name} {Variant} ({Year range})
```

Four escalation levels – always pick the **shortest one that is unambiguous in context**:

| Level | Example | When |
|---|---|---|
| 0 · Buildingline | `BMW GS` | category pages, SEO, navigation only – **never** for an individual machine |
| 1 · Model | `BMW R 1300 GS` | when only one generation/variant exists |
| 2 · + Variant | `BMW R 1300 GS Adventure` | as soon as trim lines exist |
| 3 · + Year range | `BMW R 1250 GS (2019–2023)` | as soon as the name has covered several generations |

Levels 2–3 are the normal case for humans. Type codes are only added for compatibility questions (parts, workshop).

### Year range instead of a single year

"BMW GS 2020" is worthless – in 2020 BMW sold six GS models (G 310 GS, F 750 GS, F 850 GS, F 850 GS Adventure, R 1250 GS, R 1250 GS Adventure), from 313 to 1254 cc.

| wrong | right |
|---|---|
| BMW GS 2020 | BMW R 1250 GS (2019–2023) |
| Yamaha MT-07 2022 | Yamaha MT-07 (2021–2024) |
| Honda Fireblade 2021 | Honda CBR1000RR-R Fireblade SP (2020–2023) |

Rule: **Year range = which motorcycle. Single year = which execution.** Name a single year only when the model year is actually what is meant: "BMW R 1250 GS, model year 2020, Rallye package, Style HP".

### Rendering rule: shortest unambiguous name

```
1. Start with "{Manufacturer} {Model name}"
2. Ambiguous in the target context? → + Variant
3. Still ambiguous?                 → + Year range
4. Still ambiguous?                 → + Type code
```

The target context decides: in a list of current new machines, `BMW R 1300 GS` is enough. In a used-bike list covering 2010–2026 it needs `BMW R 1300 GS (from 2023)`, because the R 1200 GS and R 1250 GS sit next to it.

→ **Store the parts separately, render them context-dependently.** No pre-built display string in the database.

### Examples

| Buildingline | Exact description |
|---|---|
| BMW GS | `BMW R 1300 GS Adventure (from 2024)` |
| BMW GS | `BMW G 310 GS (2017–2024)` |
| Yamaha MT | `Yamaha MT-07 (from 2025, Euro 5+)` |
| Honda Africa Twin | `Honda CRF1100L Africa Twin Adventure Sports DCT (from 2022)` |
| KTM Duke | `KTM 1390 Super Duke R Evo (from 2024)` |
| Ducati | `Ducati Multistrada V4 S (2021–2024)` |
| Kawasaki | `Kawasaki Z900 (2020–2024)` |

## User guidance

Non-technical users type "BMW GS" or "my 1250". That must not fail:

1. **Accept the input** at buildingline level (fuzzy, via the alias table)
2. **Ask back** when it is ambiguous – offering picture, year range and power as selection criteria, not type codes
3. **Store and display** always as an unambiguous level-3 name

Type codes (K50, RM34, SC82) stay internal and only appear for parts and technical questions.

## Sources

- [POLO – Yamaha MT-07 2014–2017 (RM04, RM17, RM18)](https://magazin.polo-motorrad.com/polo-bike-datenbank/yamaha-mt-07-2014-2017-rm04-rm17-rm18-mtn-690/)
- [Raxim – Yamaha MT-07 from 2025 (RM48–RM51), Euro 5+ & Y-AMT](https://mtp-racing.de/blog/yamaha-mt-07-from-2025-rm48-rm49-rm50-rm51-euro5-plus-y-amt-facelift-differences-accessory-compatibility)
- [cbr1000rr.de – Fireblade type codes SC28–SC82](https://www.cbr1000rr.de/)
- [Motorradonline – What changes with Euro 5+](https://www.motorradonline.de/ratgeber/euro5-plus-was-aendert-sich-mit-euro5-fuer-motorraeder/)
- [motoin – Euro 5+ emission standard from 2025](https://www.motoin.de/magazin/news/abgasnorm-euro5/)
- [mobile.de – Motorcycle search (vehicle categories)](https://www.mobile.de/s/motorrad)
- [Ultimate Motorcycling – BMW Model Letters and Numbers](https://ultimatemotorcycling.com/2020/12/26/bmw-motorcycles-what-the-model-letters-and-numbers-mean/)

---

## Implementation decisions (owner, 2026-08-31)

The domain knowledge above stays as written — it describes motorcycles, not
this application. Where **this catalogue** deliberately implements something
other than what the domain describes, it is recorded here so the deviation is a
decision and not a bug. Details and blast radius:
[`roadmap/model-naming-data-model.md`](roadmap/model-naming-data-model.md) §0,
rendering rules: [`roadmap/model-naming-display-spec.md`](roadmap/model-naming-display-spec.md).

| Domain level | Implemented as | Deviation |
|---|---|---|
| Manufacturer | `manufacturers` table | — |
| Buildingline | `motorbikes.buildingline` — a nullable **text column**, not a table (nothing points at a family, so there is no integrity to enforce) | drift is held off by a normalisation helper (case-insensitive reuse of the first-seen casing) plus the review form's suggestion list, not by a unique constraint. Promotable to a table later if a facet UI or per-family content ships |
| Model | not a row — the pair `(manufacturer, model_name)` | a marketing model is a grouping, not an entity |
| **Generation** | **one `motorbikes` row**, identified by `(manufacturer, model_name, year_from)`; slug `bmw/r-1250-gs/2019-2023` | the specs, documents, chunks and images all hang off this row |
| Type code | `motorbikes.type_codes` — a **list**, because one generation is routinely known by several codes (`FLSTF`/`FLFB`/`FLFBS`, `RM48`–`RM51`) | codes are **retrieval and lookup metadata**, not identity: ingestion records every code the sources print, they seed search terms and a resolver leg, and they are never part of the slug and never shown to a customer. Harley's codes are really *per trim*; the flat list knowingly flattens that until trims are modelled properly |
| Variant (trim) | **not a row.** The catalogue row is the **base**; every other trim is an entry in the row's `variants` JSONB carrying its name, the specifications that *differ from or are added to* the base, and a free-text `description` for gear, colours and packages | **a rendered name never contains a trim.** Trims are shown as their own element (chips + a delta line), never as words inside the name. The naming formula's level 2 (`+ Variant`) therefore has no data behind it and the rendered escalation stops at the year range: buildingline → model → model + year range |
| ModelYear | not modelled | the year *range* is on the row; per-year colours/packages/prices are a `variants` `description` at best |
| Alias table ("mandatory" above) | **not built.** Codes resolve through `type_codes`; *spellings* rely on the advisor normalising "R1300GS" → "R 1300 GS" before it calls a tool, plus a resolver that absorbs case, spacing and punctuation via `slugify` | marque abbreviations and unusual spellings stay unresolvable until a `motorbikes.aliases` metadata column is added. Trigger conditions: data-model doc §2.3 |

**Known gap that follows from the trim decision.** Specification filters match
the base row only, so a hard "≥ 15 l tank" filter can exclude a model whose
Adventure trim carries 20 l. Recorded under "Future upgrades" in
[`roadmap.md`](roadmap.md); not handled today.
