# Diagrams

This folder contains architecture and data-flow documentation for IntelliRoads in
[Mermaid](https://mermaid.js.org/) format. Every diagram is based on the real source
code — no information has been invented.

---

## Files

| File | Contents |
|---|---|
| [`architecture.md`](./architecture.md) | System component map — SUMO + TraCI, FastAPI backend, controllers (rule-based / DQN), safety layer, SQLite, WebSocket `/ws/live`, React dashboard |
| [`data-flow.md`](./data-flow.md) | Two sequence diagrams: (1) one simulation tick from SUMO to the browser screen; (2) a user switching between Standard timing and Smart AI mode |
| [`database-schema.md`](./database-schema.md) | ER diagram of all 15 real SQLite tables with column names and data types, sourced from `backend/app/core/database.py` |
| [`frontend-structure.md`](./frontend-structure.md) | Page and component map — React Router routes, `TrafficContext`, `services/api.ts`, `services/websocket.ts`, all pages and their key widgets |

---

## How to View

### On GitHub (recommended)

GitHub renders Mermaid code blocks natively in Markdown files. Open any `.md` file in this
folder on GitHub and the diagrams will appear as rendered SVGs — no extra tools needed.

### In VS Code

Install the **Markdown Preview Mermaid Support** extension
(`bierner.markdown-mermaid`). Open any file and press `Ctrl+Shift+V` (or
`Cmd+Shift+V` on macOS) to preview with rendered diagrams.

---

## How to Export to PNG

> **Note:** The command below requires internet access to download the CLI on first run.
> Only use it if your network allows `npx` to reach the npm registry.

Install and run [`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli):

```bash
# Export a single diagram (run from the repo root)
npx @mermaid-js/mermaid-cli -i docs/diagrams/architecture.md -o docs/diagrams/architecture.png

# Export all diagrams at once (bash / Git Bash / WSL)
for f in docs/diagrams/*.md; do
  npx @mermaid-js/mermaid-cli -i "$f" -o "${f%.md}.png"
done
```

The CLI reads the first `mermaid` fenced code block in each Markdown file and
produces a PNG at the specified output path.

---

## Accuracy Note

Each diagram lists the exact source files that were read to produce it. If the
backend or frontend code changes, re-read those files and update the diagram in the
same PR so the documentation stays in sync.
