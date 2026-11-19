# student.uva.nl voor AI-agents (spike)

Een statische versie van de informatiepagina's van student.uva.nl, als Markdown en simpele HTML, waarbij per opleiding duidelijk is welke informatie geldt.

## Draaien

```bash
python3 generator/fetch.py          # haalt ?allcontent-data van alle informatiepagina's op naar data/ (cache; --refresh om opnieuw te halen)
python3 generator/build.py --base-url https://<host>/<pad>   # bouwt site/
python3 -m http.server 8000 --directory site                 # lokaal bekijken (standaard base-url is http://localhost:8000)
```

Alleen de standaardbibliotheek van Python 3; geen pakketten nodig.

## Structuur van site/

- `llms.txt`: uitleg voor agents en de ingangen.
- `nl/opleidingen/index` → `nl/opleidingen/<codename>/alle-paginas`: inhoudsopgave met alle pagina's voor die opleiding, per onderwerp, met de belangrijkste kopjes (h2) van elke pagina en links naar de juiste versie.
- `nl/opleidingen/<codename>/index` (onderwerpen) → `nl/opleidingen/<codename>/<onderwerp>` (pagina's met korte beschrijving).
- `nl/informatie/<slug>`: algemene versie (wat de site zonder gekozen opleiding toont), met onderaan de links naar de versies per opleiding.
- `nl/informatie/<slug>/<naam>`: versie voor een groep opleidingen die dezelfde content zien. De naam komt uit de taxonomie `study_programmes`: de codename van de opleiding of het tussenniveau (`fdr_masters`, `fmg_psychologie`) als de groep daar precies op past, maximaal drie knopen verbonden met `+`, en anders het kleinste omvattende niveau met een volgnummer (`feb-2`).
- `nl/onderwerpen/<onderwerp>`: algemene versies per onderwerp.
- Engels: `en/programmes`, `en/information`, `en/topics`.
- Elke pagina bestaat als `.md` en `.html`; plus `sitemap.xml` en `robots.txt`.

## Hoe de filtering werkt

Elk blok in de paginadata heeft een lijst `studies`. Een student van opleiding X ziet de blokken waarin X of `alle_opleidingen` staat (ook genest in harmonica-items en stappen van het stappenplan). Opleidingen die precies dezelfde content zien, delen één bestand.

## Meting

`meting/` bevat het meetscript en de resultaten per pagina.
