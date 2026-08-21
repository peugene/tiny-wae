---
description: Convertir un .md en page .html lisible/imprimable (roadmap, revue, doc)
---
Convertis en HTML le fichier Markdown : $ARGUMENTS.

```bash
just md2html <source>.md <dest>.html "Titre" "Bandeau"
```

Sert aux `roadmap.html` / `revue.html` des chantiers et aux docs d'analyse. Le dashboard lie
automatiquement les `*.html` d'un chantier. Convention : **.md = canal agents, .html = vue
humaine** — ne jamais éditer le `.html` à la main.
