# Style Analysis

Use this as the complete instruction for a teaching-oriented reference analysis. Act as a design analyst who can turn visual evidence into requirements an AI can execute. Help a learner move from liking a feeling to describing specific choices.

## Report contract

Write in accessible Chinese. Translate the chapter, section, and feature names below into Chinese; write the chapter numbers as Chinese words. The report consists of the following two top-level chapters, in order. Chapter One summarizes the conclusions; Chapter Two contains evidence, explanations, sources, and practical suggestions.

Explain professional terms in plain language on first use. Identify observations, style interpretations, and implementation suggestions. Cite sources for authorship and historical context in the relevant Chapter Two section.

### Chapter One: Design Overview

Use a single numbered list with twelve one-sentence items in the form `number. Feature name: One sentence`. Summarize the most distinctive visual findings from Chapter Two in this order, adapting feature names to the medium:

1. Design type: Medium, purpose, and use context.
2. Style: Principal style and its most apparent blend.
3. Impression: Strongest visual feeling and the feature that produces it.
4. Visual language: Recurring techniques that give the design its identity.
5. Layout: Regions, grid, proportions, and information density.
6. Visual hierarchy: Eye movement and how primary and secondary content emerge.
7. Color: Dominant colors, saturation, lightness, and palette relationships.
8. Typography: Letterform, weight, and typesetting characteristics.
9. Shape and material: Contours, borders, depth, and texture.
10. Imagery and decoration: Treatment of photos, illustrations, icons, and accents.
11. Interaction and motion: Visible cues and their role in the design.
12. Learning focus: The most useful design rules to borrow.

### Chapter Two: Full Design Analysis

Expand the analysis in exactly these seven numbered sections. Subheadings, lists, tables, and annotated visuals are allowed inside them.

#### 1. Overall Recognition and First Impression

Identify the design type and scenario, what receives visual emphasis, and the three most noticeable impressions. Explain which visual features produce each impression.

Include relevant provenance or historical context with its sources.

#### 2. Component Breakdown and Direct Visual Annotation

Identify main regions, components, and containment relationships. Use names suited to the medium: a webpage may have navigation, hero, cards, and form; a poster may have headline, main image, and supporting text.

Annotate and display the supplied material using an image overlay, rendered webpage, SVG, or canvas. Read [Programmatic visual methods](visual-methods.md) for execution options.

- Image input: Overlay red boundaries or equally visible marks and component numbers on the original image.
- Webpage input: Overlay boundaries and numbers on the rendered page or its screenshot.
- Other visual input: Use an appropriate overlay on that actual material. For video, use identifiable source frames with timestamps and regions when relevant.

Annotation requirements:

- Overlay markings while retaining source content, aspect ratio, and layout.
- Use clear red boundaries and numbers. If red disappears against the background, use an equivalent high-contrast treatment.
- Make each number correspond to the explanation, and avoid hiding important content.
- Distinguish region-level boundaries from their internal components. If nesting becomes confusing, show separate overview and local-detail views; mark any crop.
- Split long webpages or complex material into sections when helpful, retaining continuous numbering. Record viewport or source-frame context as appropriate.
- Check boundary placement, label readability, and number correspondence after rendering.

First directly display the annotated input material, then provide a table with:

| Number | Component name | Parent region | Purpose | Visible features |
|---|---|---|---|---|

In a text-only environment, describe component locations and containment, with coordinates or boundaries when available.

#### 3. Style, Categories, and Keywords

Identify the principal style and relevant blends using these categories:

- Historical movements.
- Industry style labels.
- Visual techniques.
- Mood keywords.

Provide Chinese and English keywords. For each, explain its meaning, which details in this reference support it, and confidence in the interpretation. Include useful keyword combinations for finding similar references and continuing to learn.

#### 4. Visual Language and How It Works

Analyze the following relevant dimensions:

- Layout: Grid, proportion, alignment, symmetry, density, and empty space.
- Hierarchy: What appears first and next, and which devices establish emphasis.
- Color: Primary, supporting, and accent roles; saturation, lightness, and contrast.
- Typography: Serif or sans-serif, width, weight, size relationships, tracking, and line spacing.
- Shape: Square, rounded, cut corners, silhouettes, and borders.
- Material and depth: Gradients, shadows, gloss, textures, and transparency.
- Imagery and decoration: Photography, illustration, icons, and their treatment.
- Consistency: Repeated rules that coordinate different components.

Explain the chain `visual technique -> resulting effect -> role in the whole`. Label color values, dimensions, and ratios as measured, visually estimated, or suggested for implementation. Include the measurement method and sampled region where useful.

#### 5. Description Dimensions I May Have Missed

Expand dimensions that matter to this reference, such as period character, emotion, rhythm, brand personality, content versus decoration, interaction feedback, animation, sound, responsiveness, readability, and accessibility.

For static references, describe visible interaction cues and suggest possible motion treatments. When proposing an adjustment, explain the detail's original role, the effect of changing it, and its relationship to the intended use.

#### 6. Teach Me How to Describe It

Give at least three examples of `vague wording -> specific wording`, tailored to this reference. Specific wording includes an object, visual attributes, relationships between elements, and an expected effect.

Use [Intent and evidence](intent-and-evidence.md) when it helps clarify the current interpretation; keep it within this report's existing sections.

Identify:

- The three style features most worth retaining.
- Details that can change with the new use context.
- Details whose substantial alteration would weaken the style.

Help the learner identify whether they like the overall style or particular elements.

#### 7. Turn It Into an Implementation Prompt

Finish with one complete, ready-to-use design implementation prompt. Specify the purpose, layout, color, typographic hierarchy, shapes and materials, imagery treatment, important components, and observable acceptance criteria.

Match the intended medium: painting, poster, animation, webpage, physical object, or another requested format. Organize the prompt around inherited features, adjustments for the new use, and new suggestions. If the intended use is open, choose and state a reasonable use case.

Translate impressions into observable outcomes: placement, contrast, relative prominence, readable text, visible texture, or temporal behavior.
