# Mermaid Diagram Usage Guide

## How to View the Diagrams

The `.mmd` files in this directory contain Mermaid diagram syntax. To view them:

### Option 1: Online Mermaid Editor
1. Go to https://mermaid.live/
2. **Enable the "Playground" option** (toggle in the interface) - this is required for the diagrams to render
3. Open the `.mmd` file in a text editor
4. Copy the **entire contents** of the file (starting from `sequenceDiagram`, `stateDiagram-v2`, `flowchart TD`, or `graph TB`)
5. Paste into the Mermaid editor
6. **Do NOT include markdown code fences** (```) - just paste the raw Mermaid syntax
7. The diagram should render automatically once playground mode is enabled

### Option 2: VS Code Extension
1. Install the "Markdown Preview Mermaid Support" extension
2. Open the `.mmd` file
3. The diagram should render automatically

### Option 3: Generate SVG Files
Use the provided conversion scripts:
```bash
./convert-mermaid.sh
# or
python convert-mermaid.py
```

This will generate `.svg` files that can be viewed in any image viewer or browser.

## Common Issues

### Error: "No diagram type detected"
- **Cause**: Including markdown code fences (```) when pasting
- **Solution**: Copy only the Mermaid syntax, not the markdown wrapper

### Error: "UnknownDiagramError"
- **Cause**: Invalid syntax or unsupported features
- **Solution**: Ensure you're using a recent version of Mermaid (v9.0+)

### Diagrams Not Rendering
- **On mermaid.live**: Make sure the "Playground" option is enabled (toggle in the interface)
- Check that the file starts with a valid diagram type declaration
- Ensure no HTML tags like `<br/>` are used (use plain text instead)
- Verify all brackets and quotes are properly matched
- Try refreshing the page after enabling playground mode

## Diagram Types

- **01-state-machine.mmd**: State diagram (`stateDiagram-v2`)
- **02-sequence-diagram.mmd**: Sequence diagram (`sequenceDiagram`)
- **03-process-flowchart.mmd**: Flowchart (`flowchart TD`)
- **04-component-interaction.mmd**: Component diagram (`graph TB`)
- **05-end-to-end-sequence.mmd**: Sequence diagram (`sequenceDiagram`)

## File Locations

- **Appliance**: `/appliance/org-join-process/*.mmd`
- **Organization Manager**: `/organization_manager/org-join-process/*.mmd`
- **Onboarding Worker**: `/onboarding-worker/org-join-process/*.mmd`
