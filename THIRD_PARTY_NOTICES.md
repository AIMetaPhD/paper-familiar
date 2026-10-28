# Third-party notices

PaperFamiliar is MIT-licensed. It depends on the following packages at runtime:

| Package | License | Use |
|---|---|---|
| FastAPI | MIT | local HTTP API |
| Starlette | BSD-3-Clause | ASGI toolkit used by FastAPI |
| Uvicorn | BSD-3-Clause | ASGI server |
| Pydantic / pydantic-core | MIT | request/response models |
| pylatexenc | MIT | optional LaTeX decoding helper |
| bibtexparser | MIT | optional bibliography cross-check |
| python-multipart | Apache-2.0 | form parsing support |

The frontend is built with React and Vite (both MIT) and ships as static assets; no runtime
Node dependency is required.

## Optional, not distributed

- `papercheck` (MIT) — optional CLI cross-check; installed by the user.
- `academic-refchecker` (MIT package) — optional metadata tool. It pulls `fuzzywuzzy`
  (**GPLv2**) and `python-Levenshtein` (**GPL-2.0-or-later**), so it is deliberately **not**
  bundled with this project.
- `pystylometry` (MIT), `faststylometry` (MIT) — experiments only.

If you enable an optional integration, its license and notices apply to your installation.
