# Contributing & project conventions

Follow these conventions for every change — UI, backend, docs, or config.

## 1. Light and dark theme compatibility

All new or updated **UI components** must work in both themes (`data-theme="light"` and `data-theme="dark"`).

- Use theme tokens from `web/src/index.css` (`--color-surface`, `--color-border`, `--color-text`, `--color-text-muted`, etc.) — not hardcoded Tailwind light colors like `bg-zinc-50`, `bg-white`, `border-zinc-200`, `text-zinc-900`.
- Prefer existing patterns: `.card`, `.btn`, `.input`, `.textarea`, `.sidebar-panel`, and shared themed classes (e.g. `catalog-themed-box`, `mcp-list-item`).
- Add reusable themed classes in `index.css` when a pattern repeats across pages.
- Verify both themes before finishing UI work (Settings → Theme, or system preference).

```tsx
// Avoid
<div className="rounded-lg border border-zinc-200 bg-zinc-50" />

// Prefer
<div className="mcp-themed-box" />
// or inline: style={{ background: "var(--color-surface-subtle)", borderColor: "var(--color-border)" }}
```

## 2. Sensitive content & gitignore

Never commit secrets or environment-specific credentials.

- Keep API keys, passwords, connection strings, TLS certs, and personal AWS deploy files **local only**.
- Use tracked templates: `.env.example`, `saved_db_connections.json.example`, `deploy.example/`.
- When introducing a new local-only file type, add it to **`.gitignore`** and document it in [secrets.md](secrets.md) (and `.env.example` if relevant).
- Do not commit generated artifacts (`outputs/`, `web/dist/`, `*.tsbuildinfo`, logs, PIDs).

See also [secrets.md](secrets.md) and the root README **Keep private** section.

## 3. Update docs for major functionality

When you add or materially change a feature, update documentation in the same PR/commit batch:

| Change type | Update |
|-------------|--------|
| New page, API route, or user workflow | [user-guide.md](user-guide.md), root [README.md](../README.md) if user-facing |
| MCP tools/resources/prompts | [mcp.md](mcp.md) |
| Architecture / data flow | [architecture.md](architecture.md) |
| Setup, env vars, Docker | [installation.md](installation.md), `.env.example` |
| Database schema | `migrations/`, [catalog-database.md](catalog-database.md) |
| AWS deploy | `deploy.example/`, [deploy-ecs.md](deploy-ecs.md) |
| Troubleshooting-worthy behavior | [troubleshooting.md](troubleshooting.md) |

Minor bug fixes and internal refactors do not require doc updates unless behavior visible to users changes.

## 4. Consistent look and feel

Match existing UI patterns — do not introduce one-off styling.

- **Layout**: `PageHeader`, sidebar panels (`AskRetrievalPanel` pattern), `.card` / `.card-pad`, page-specific splits (`.mcp-page-split`, `.agents-page-split`).
- **Forms**: `.label`, `.input`, `.select`, `.textarea`, `.field`, `.btn` / `.btn-secondary`.
- **Lists & panels**: themed boxes with `var(--color-surface-subtle)` and `var(--color-border)`; reuse or extend classes in `index.css`.
- **Spacing & radius**: `rounded-xl` for cards, `rounded-lg` for inner panels; follow neighboring components on the same page.
- **Copy**: short labels, sentence-case headings, muted helper text via `--color-text-muted`.

When in doubt, open an existing page (Ask, Catalog, MCP, Agents) and mirror its structure before adding new chrome.
