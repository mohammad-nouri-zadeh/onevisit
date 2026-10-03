# onevisit_ui: design system

Token, componenti CSS, font e script locali condivisi da `assistant_web`, `dashboard` e `gateway`.
Guida completa: [docs/design-system.md](../../docs/design-system.md).

```python
from fastapi.staticfiles import StaticFiles
import onevisit_ui

app.mount(onevisit_ui.MOUNT_PATH, StaticFiles(directory=onevisit_ui.STATIC_DIR), name="ui")
```

```html
<link rel="stylesheet" href="/ui/fonts.css">
<link rel="stylesheet" href="/ui/onevisit.css">
<script src="/ui/vendor/htmx.min.js" defer></script>
```
