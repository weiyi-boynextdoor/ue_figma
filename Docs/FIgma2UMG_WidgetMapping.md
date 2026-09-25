
# Figma to UMG widget mapping

The mappings below reflect the Figma2UMG plugin source in this project. Widget selection depends on the Figma node type, layout settings, and component properties. A single node can generate multiple widgets through wrappers.

| Figma node / condition | Generated UMG widget |
|---|---|
| Text | `UTextBlock` |
| Rectangle, ellipse | `UImage`, using a brush/material or exported texture |
| Vector, line, polygon, star, Boolean operation, Washi tape | `UImage`, generally using an exported texture |
| Frame / group without Auto Layout | `UCanvasPanel` |
| Horizontal Auto Layout, no wrapping | `UHorizontalBox` |
| Vertical Auto Layout, no wrapping | `UVerticalBox` |
| Horizontal / vertical Auto Layout with wrapping | `UWrapBox` |
| Frame / group with fixed width or height | Additional `USizeBox` wrapper, except when generating a button |
| Frame / group with visible fills or strokes | Additional `UBorder` wrapper, except when generating a button or when the direct parent is a component set |
| Frame / group matching button-generation rules, or with a nonempty `TransitionNodeID` | `UButton` containing its layout, when frame-button generation is allowed |
| Component, or frame exported as a separate Widget Blueprint | `UUserWidget` when referenced; its internal layout follows the frame rules |
| Component instance | `UUserWidget` referencing the generated component blueprint |
| Instance whose source component is missing | `UImage` texture placeholder |
| Instance-swap property | `UWidgetSwitcher` containing the preferred component choices |
| Component set with ordinary variants, imported as root | `UWidgetSwitcher` |
| Component set with a variant property containing both `Hovered` and `Pressed`, imported as root | `UButton`, using the named state variants (`Default`, `Hovered`, `Pressed`, `Disabled`, and `Focused`) |
| Non-button component set embedded in another layout | `UCanvasPanel` containing its children; button component sets are omitted in this context |
| Figma page (`CANVAS`) | `UCanvasPanel` |
| Section | `UCanvasPanel`, optionally wrapped in `UBorder` |
| Document with multiple children | `UWidgetSwitcher`; a single child is used directly |

These are the default widget classes. The plugin also supports subclass overrides through [ClassOverrides.h](Plugins/Figma2UMG/Source/Figma2UMG/Public/Settings/ClassOverrides.h).

### Source references

- [FigmaGroup.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaGroup.cpp): layout panels, size/border wrappers, and frame/group buttons.
- [FigmaFrame.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaFrame.cpp): references to separately generated Widget Blueprints.
- [FigmaInstance.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaInstance.cpp): component instances, instance swapping, and missing-component placeholders.
- [FigmaComponentSet.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaComponentSet.cpp): variant switching and button states.
- [FigmaComponentPropertyDefinition.h](Plugins/Figma2UMG/Source/Figma2UMG/Public/Parser/Properties/FigmaComponentPropertyDefinition.h): button-variant detection.
- [Vector node implementations](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/Vectors): text, shapes, and image generation.
- [FigmaCanvas.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaCanvas.cpp), [FigmaSection.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaSection.cpp), and [FigmaDocument.cpp](Plugins/Figma2UMG/Source/Figma2UMG/Private/Parser/Nodes/FigmaDocument.cpp): page, section, and document containers.
