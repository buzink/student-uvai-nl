"""Build a static, agent-friendly version of the information pages of student.uva.nl.

Reads the page data downloaded by fetch.py and writes Markdown (.md) and simple HTML (.html)
for every page: one general version, plus one version per distinct set of study-specific
content (deduplicated: studies that see the same content share one file). Every study gets an
index, grouped by the topics from the breadcrumb, that links straight to the right version.

Usage: python3 build.py [--data data] [--out site] [--base-url https://example.github.io/repo]
"""
import argparse, datetime, glob, html, json, os, re, shutil
from collections import OrderedDict, defaultdict
from html.parser import HTMLParser

SOURCE = 'https://student.uva.nl'
ALL = 'alle_opleidingen'
CONTENT_KEYS = ['introductionText', 'resolvedCallToActions', 'genericBodyText', 'resolvedTargetedBodyTexts',
                'roadMap', 'resolvedTargetedHarmonicas', 'genericBodyText2', 'resolvedTargetedBodyTexts2',
                'resolvedVideoImageTexts', 'resolvedQuotes', 'resolvedContacts']

T = {
    'nl': dict(info='informatie', prog='opleidingen', topics='onderwerpen', other='overig',
               site_title='student.uva.nl voor AI-agents',
               programmes='Opleidingen', topics_title='Onderwerpen', general='algemene versie',
               applies='Geldt voor', contact='Contact', step='Stap', more_info='Informatie per opleiding',
               generic_note='De inhoud van deze pagina verschilt per opleiding. Hieronder staat alleen de inleiding; lees de volledige informatie in de versie voor de opleiding van de student (zie "Informatie per opleiding"), of begin bij {link}.',
               only_general='Deze pagina is voor alle opleidingen hetzelfde.',
               specific='eigen info',
               study_intro='Alle informatiepagina\'s van student.uva.nl voor <strong>{label}</strong>, per onderwerp. De links gaan direct naar de versie voor deze opleiding.',
               topic_intro='Pagina\'s over {topic} voor <strong>{label}</strong>. Links gaan direct naar de versie voor deze opleiding. "(eigen info)": de pagina heeft voor deze opleiding andere of extra informatie dan de algemene versie.',
               generic_topic_intro='Pagina\'s over {topic} (algemene versies). Informatie verschilt vaak per opleiding: begin voor de juiste versie bij {link}.',
               prog_intro='Kies de opleiding van de student. Elke opleiding heeft een eigen index met links naar de juiste versie van elke pagina.',
               footer='Experimentele versie, automatisch gemaakt uit {src} op {date}. Bij twijfel geldt student.uva.nl.',
               pages='pagina\'s', with_specific='met opleidingsspecifieke info', source='Bron'),
    'en': dict(info='information', prog='programmes', topics='topics', other='other',
               site_title='student.uva.nl for AI agents',
               programmes='Programmes', topics_title='Topics', general='general version',
               applies='Applies to', contact='Contact', step='Step', more_info='Information per programme',
               generic_note='The content of this page differs per programme. Below is only the introduction; read the full information in the version for the student\'s programme (see "Information per programme"), or start at {link}.',
               only_general='This page is the same for all programmes.',
               specific='own info',
               study_intro='All information pages of student.uva.nl for <strong>{label}</strong>, by topic. Links go straight to the version for this programme.',
               topic_intro='Pages about {topic} for <strong>{label}</strong>. Links go straight to the version for this programme. "(own info)": the page has different or additional information for this programme compared to the general version.',
               generic_topic_intro='Pages about {topic} (general versions). Information often differs per programme: for the right version, start at {link}.',
               prog_intro='Choose the student\'s programme. Each programme has its own index that links to the right version of every page.',
               footer='Experimental version, generated automatically from {src} on {date}. If in doubt, student.uva.nl prevails.',
               pages='pages', with_specific='with programme-specific info', source='Source'),
}

# ---------------------------------------------------------------- rich text

VOID = {'br', 'img', 'hr', 'source'}
BLOCK = {'p', 'div', 'section', 'aside', 'blockquote', 'ul', 'ol', 'li', 'table', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figure'}


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = ('root', {}, []); self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = (tag, dict(attrs), [])
        self.stack[-1][2].append(node)
        if tag not in VOID: self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; return

    def handle_data(self, data):
        self.stack[-1][2].append(data)


def parse(s):
    t = Tree(); t.feed(s or ''); t.close(); return t.root


def wrap(inner, mark):
    """Emphasis around the text, with surrounding spaces kept outside the markers (Markdown needs that)."""
    t = inner.strip()
    if not t: return inner
    return (' ' if inner[:1].isspace() else '') + mark + t + mark + (' ' if inner[-1:].isspace() else '')


def ws(s):
    return re.sub(r'[ \t\r\n ]+', ' ', s)


class Renderer:
    """Renders a parsed tree to Markdown or to clean HTML. `link` maps an href to a final URL."""

    def __init__(self, link):
        self.link = link

    # -- markdown
    def md(self, node):
        out = self._md_block(node[2], 0)
        out = re.sub(r'[ \t]+\n', '\n', out)
        return re.sub(r'\n{3,}', '\n\n', out).strip()

    def _md_inline(self, children):
        s = ''
        for c in children:
            if isinstance(c, str): s += ws(c); continue
            tag, attrs, kids = c
            inner = self._md_inline(kids)
            if tag == 'a':
                href = self.link(attrs.get('href') or '')
                # Parentheses and spaces would end a Markdown link early (e.g. DataNose URLs).
                href = href.replace(' ', '%20').replace('(', '%28').replace(')', '%29')
                s += f'[{inner.strip()}]({href})' if href and inner.strip() else inner
            elif tag in ('strong', 'b'):
                s += wrap(inner, '**')
            elif tag in ('em', 'i'):
                s += wrap(inner, '*')
            elif tag == 'br':
                s += '  \n'
            elif tag in ('img', 'video', 'source', 'script', 'style'):
                continue
            else:
                s += inner
        return s

    def _md_block(self, children, depth):
        out, inline = [], []

        def flush():
            if inline:
                t = self._md_inline(inline).strip()
                if t: out.append(t + '\n\n')
                inline.clear()

        for c in children:
            if isinstance(c, str) or c[0] not in BLOCK:
                inline.append(c); continue
            flush()
            tag, attrs, kids = c
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                t = self._md_inline(kids).strip().strip('*').strip()
                if t: out.append('#' * min(int(tag[1]) + 0, 6) + ' ' + t + '\n\n')
            elif tag in ('ul', 'ol'):
                n = 0
                for li in kids:
                    if isinstance(li, str) or li[0] != 'li': continue
                    n += 1
                    bullet = f'{n}.' if tag == 'ol' else '-'
                    body = self._md_block(li[2], depth + 1).strip()
                    lines = body.split('\n')
                    pad = '  ' * (depth + 1)
                    out.append('  ' * depth + bullet + ' ' + lines[0] + '\n' +
                               ''.join((pad + l if l.strip() else '') + '\n' for l in lines[1:] if l.strip()))
                out.append('\n')
            elif tag == 'table':
                rows = [r for r in self._find(c, 'tr')]
                cells = [[self._md_inline(td[2]).strip().replace('|', '/').replace('\n', ' ')
                          for td in r[2] if not isinstance(td, str) and td[0] in ('td', 'th')] for r in rows]
                cells = [r for r in cells if any(r)]
                if cells:
                    w = max(len(r) for r in cells)
                    cells = [r + [''] * (w - len(r)) for r in cells]
                    out.append('| ' + ' | '.join(cells[0]) + ' |\n|' + '---|' * w + '\n')
                    out += ['| ' + ' | '.join(r) + ' |\n' for r in cells[1:]]
                    out.append('\n')
            elif tag in ('aside', 'blockquote'):
                body = self._md_block(kids, depth).strip()
                out.append('\n'.join('> ' + l if l else '>' for l in body.split('\n')) + '\n\n')
            else:  # p, div, section, li, figure
                out.append(self._md_block(kids, depth))
        flush()
        return ''.join(out)

    def _find(self, node, tag):
        for c in node[2]:
            if isinstance(c, str): continue
            if c[0] == tag: yield c
            else: yield from self._find(c, tag)

    # -- clean html
    KEEP = {'p', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'b', 'i', 'br', 'table',
            'thead', 'tbody', 'tr', 'td', 'th', 'blockquote', 'aside', 'sup', 'sub', 'a'}

    def html(self, node):
        return self._html(node[2]).strip()

    def _html(self, children):
        s = ''
        for c in children:
            if isinstance(c, str): s += html.escape(ws(c), quote=False); continue
            tag, attrs, kids = c
            if tag in ('img', 'video', 'source', 'script', 'style'): continue
            inner = self._html(kids)
            if tag not in self.KEEP: s += inner; continue
            if tag == 'br': s += '<br>'; continue
            if tag == 'a':
                href = self.link(attrs.get('href') or '')
                s += f'<a href="{html.escape(href)}">{inner}</a>' if href else inner; continue
            if tag in ('p', 'li', 'td', 'th') or tag.startswith('h'):
                if not inner.strip() and tag != 'td' and tag != 'th': continue
            s += f'<{tag}>{inner}</{tag}>' + ('\n' if tag in BLOCK or tag == 'tr' else '')
        return s


# ---------------------------------------------------------------- page model

def filt(o, study):
    """What a student of `study` sees (None = default view: only blocks for all programmes)."""
    if isinstance(o, dict):
        st = o.get('studies')
        if isinstance(st, list) and st and ALL not in st and (study is None or study not in st):
            return None
        return {k: filt(v, study) for k, v in o.items() if k != 'studies'}
    if isinstance(o, list):
        return [x for x in (filt(v, study) for v in o) if x is not None]
    return o


def e(s):
    return html.escape(s or '', quote=True)


def content_html(c, t):
    """Turn the (filtered) content fields of an information page into one HTML string."""
    h = []
    if c.get('introductionText'): h.append(f'<p><strong>{e(c["introductionText"])}</strong></p>')
    for cta in c.get('resolvedCallToActions') or []:
        parts = [f'<strong>{e(cta.get("title"))}</strong>' if cta.get('title') else '', e(cta.get('description'))]
        url = cta.get('url') or cta.get('slug')
        link = f'<a href="{e(url)}">{e(cta.get("urlText") or url)}</a>' if url else ''
        h.append('<p>' + ' – '.join(x for x in parts + [link] if x) + '</p>')
    h.append(c.get('genericBodyText') or '')
    h += [b.get('richText') or '' for b in c.get('resolvedTargetedBodyTexts') or []]
    # Order as on student.uva.nl: harmonicas (accordions) before the roadmap (step-by-step plan).
    for hm in c.get('resolvedTargetedHarmonicas') or []:
        if hm.get('title'): h.append(f'<h2>{e(hm["title"])}</h2>')
        for it in hm.get('items') or []:
            h.append(f'<h3>{e(it.get("title"))}</h3>')
            h.append(it.get('richText') or '')
            h += [x.get('richText') or '' for x in it.get('targetedRichText') or []]
    rm = c.get('roadMap') or {}
    if rm.get('resolvedSteps'):
        if rm.get('title'): h.append(f'<h2>{e(rm["title"])}</h2>')
        h.append(rm.get('introductionText') or '')
        for i, s in enumerate(rm['resolvedSteps'], 1):
            h.append(f'<h3>{t["step"]} {i}: {e((s.get("title") or "").strip())}</h3>')
            h.append(s.get('richText') or '')
            h += [x.get('richText') or '' for x in s.get('resolvedTargetedRichText') or []]
    h.append(c.get('genericBodyText2') or '')
    h += [b.get('richText') or '' for b in c.get('resolvedTargetedBodyTexts2') or []]
    for v in c.get('resolvedVideoImageTexts') or []:
        if v.get('title'): h.append(f'<h3>{e(v["title"])}</h3>')
        h.append(v.get('bodyText') or '')
    for q in c.get('resolvedQuotes') or []:
        h.append(f'<blockquote><p>{e(q.get("text"))}</p><p>– {e(q.get("name"))}{", " + e(q["role"]) if q.get("role") else ""}</p></blockquote>')
    contacts = c.get('resolvedContacts') or []
    if contacts:
        h.append(f'<h2>{t["contact"]}</h2>')
        for ct in contacts:
            h.append(f'<h3>{e(ct.get("name"))}</h3>')
            sub = ', '.join(x for x in (ct.get('role'), ct.get('department')) if x)
            if sub: h.append(f'<p>{e(sub)}</p>')
            h.append(ct.get('description') or '')
            li = []
            em = ct.get('email') or {}
            if em.get('value'): li.append(f'E-mail: <a href="mailto:{e(em["value"])}">{e(em["value"])}</a> {strip_p(em.get("description"))}')
            ph = ct.get('phoneNumber') or {}
            if isinstance(ph, dict) and ph.get('value'): li.append(f'Tel: {e(ph["value"])} {strip_p(ph.get("description"))}')
            wa = ct.get('whatsApp') or {}
            if isinstance(wa, dict) and wa.get('value'): li.append(f'WhatsApp: {e(wa["value"])}')
            ch = ct.get('chat') or {}
            if ch.get('chatEnabled'): li.append('Chat: ' + (strip_p(ch.get('extraInformation')) or 'student.uva.nl'))
            for key, label in (('visitingAddress', 'Bezoek'), ('postalAddress', 'Post')):
                ad = ct.get(key) or {}
                if isinstance(ad, dict) and (ad.get('address') or ad.get('description')):
                    li.append(f'{label}: {strip_p(ad.get("address"))} {strip_p(ad.get("description"))}')  # both are rich text
            om = ct.get('onlineMeeting') or {}
            if isinstance(om, dict) and om.get('url'): li.append(f'Online: <a href="{e(om["url"])}">{e(om.get("urlText") or om["url"])}</a>')
            if li: h.append('<ul>' + ''.join(f'<li>{x}</li>' for x in li) + '</ul>')
    return '\n'.join(x for x in h if x)


def short(desc, limit=80):
    """First sentence of a description, cut at a word boundary: enough to choose a page, cheap in link lists."""
    s = re.split(r'(?<=[.!?])\s', (desc or '').strip(), maxsplit=1)[0]
    if len(s) <= limit: return s
    return s[:limit].rsplit(' ', 1)[0].rstrip(',;:') + '…'


def strip_p(s):
    return re.sub(r'</?p>', ' ', s or '').strip()


# ---------------------------------------------------------------- taxonomy names

class Taxonomy:
    """The study_programmes taxonomy, used to name a variant after the levels editors tag with
    (a faculty, 'fdr_masters', ...), so the file name says for whom it is and stays stable."""

    MAX_NODES = 3

    def __init__(self, fn):
        self.leaves, self.depth, self.name, self.order = {}, {}, {}, {}
        if not os.path.exists(fn): return

        def walk(t, d):
            self.name[t['codename']] = t['name']; self.depth[t['codename']] = d
            self.order[t['codename']] = len(self.order)
            s = set()
            for c in t['terms']: s |= walk(c, d + 1)
            self.leaves[t['codename']] = frozenset(s or {t['codename']})
            return self.leaves[t['codename']]
        for term in json.load(open(fn))['terms']: walk(term, 0)

    def cover(self, group):
        """Fewest, highest nodes whose programmes together are exactly `group` (None if a programme is unknown)."""
        g = set(group)
        if not self.leaves or not g <= self.leaves.get(ALL, frozenset()): return None
        chosen = []
        for node in sorted(self.leaves, key=lambda k: (self.depth[k], self.order[k])):
            if self.leaves[node] <= g and not any(self.leaves[node] <= self.leaves[c] for c in chosen):
                chosen.append(node)
        return sorted(chosen, key=self.order.get)

    def variant_name(self, group, fallback_count):
        """(file name, title label). One to three nodes: their codenames joined by '+'.
        Otherwise the smallest node containing the whole group plus a number, e.g. 'feb-2'."""
        nodes = self.cover(group)
        if nodes and len(nodes) <= self.MAX_NODES:
            return '+'.join(nodes), ', '.join(self.name[n] for n in nodes)
        g = set(group)
        parents = [n for n in self.leaves if g <= self.leaves[n]] if nodes is not None else []
        base = min(parents, key=lambda n: (len(self.leaves[n]), -self.depth[n])) if parents else 'groep'
        fallback_count[base] += 1
        return f'{base}-{fallback_count[base]}', None


# ---------------------------------------------------------------- site

class Site:
    def __init__(self, data, out, base):
        self.out, self.base = out, base.rstrip('/')
        self.date = datetime.date.today().isoformat()
        self.pages = {'nl': {}, 'en': {}}
        for f in sorted(glob.glob(os.path.join(data, 'pages', '*.json'))):
            d = json.load(open(f))
            if d['page']: self.pages[d['lang']][d['slug']] = d['page']
        self.files = 0; self.bytes = 0; self.html_urls = []
        self.tax = Taxonomy(os.path.join(data, 'taxonomy_study_programmes.json'))

    # -- urls
    def url(self, path, ext, frm=None):
        """Absolute URL, or, with `frm` (the path of the linking page), a relative one: far fewer tokens in link lists."""
        if frm is None: return f'{self.base}/{path}.{ext}'
        return os.path.relpath(f'{path}.{ext}', os.path.dirname(frm) or '.')

    def link_fn(self, lang, ext, frm):
        def link(href):
            href = html.unescape(href or '').strip()
            if not href or href.startswith('#'): return ''
            if href.startswith('site:'): return self.url(href[5:], ext, frm)
            m = re.match(r'^(?:https?://student\.uva\.nl)?/(?:(en)/information|informatie)/([^?#]+)', href)
            if m:
                l = m.group(1) or 'nl'; slug = m.group(2).rstrip('/')
                if slug in self.pages[l]: return self.url(f'{l}/{T[l]["info"]}/{slug}', ext, frm)
            if href.startswith('/'): return SOURCE + href
            return href
        return link

    # -- writing
    def write(self, lang, path, title, body_html, meta=None, description=''):
        meta = meta or {}
        for ext in ('md', 'html'):
            r = Renderer(self.link_fn(lang, ext, path))
            tree = parse(body_html)
            fn = os.path.join(self.out, path + '.' + ext)
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            footer = T[lang]['footer'].format(src=meta.get('source', SOURCE), date=self.date)
            if ext == 'md':
                fm = ''.join(f'{k}: {json.dumps(v, ensure_ascii=False)}\n' for k, v in meta.items() if v)
                doc = f'---\ntitle: {json.dumps(title, ensure_ascii=False)}\n{fm}---\n\n# {title}\n\n{r.md(tree)}\n\n---\n{footer}\n'
            else:
                alt = f'<link rel="alternate" type="text/markdown" href="{e(self.url(path, "md"))}">'
                tr = meta.get('translation')
                if tr: alt += f'\n<link rel="alternate" hreflang="{"en" if lang == "nl" else "nl"}" href="{e(tr.replace(".md", ".html"))}">'
                doc = (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
                       f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{e(title)}</title>\n'
                       f'<meta name="description" content="{e(description)}">\n{alt}\n'
                       '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#222;background:#fff}'
                       'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.25rem .5rem}aside,blockquote{border-left:3px solid #bc0031;margin-left:0;padding-left:1rem}</style>\n'
                       f'</head>\n<body>\n<main>\n<h1>{e(title)}</h1>\n{r.html(tree)}\n</main>\n'
                       f'<footer><hr><p><small>{e(footer)}</small></p></footer>\n</body>\n</html>\n')
                self.html_urls.append(self.url(path, 'html'))
            open(fn, 'w').write(doc)
            self.files += 1; self.bytes += len(doc.encode())

    # -- build
    def build(self):
        if os.path.exists(self.out): shutil.rmtree(self.out)
        os.makedirs(self.out)
        summary = {}
        for lang in ('nl', 'en'):
            summary[lang] = self.build_lang(lang)
        self.write_root(summary)
        return summary

    def build_lang(self, lang):
        t = T[lang]; pages = self.pages[lang]
        studies = OrderedDict()  # codename -> label, in taxonomy order
        for p in sorted(pages.values(), key=lambda p: -len(p.get('resolvedStudies') or [])):
            for s in p.get('resolvedStudies') or []:
                if s['value'] != ALL: studies.setdefault(s['value'], s['label'])
        topics = OrderedDict()  # topic slug -> label
        by_study = defaultdict(list)  # study -> [(topic, sub, slug, title, desc, target_path, specific)]
        generic_by_topic = defaultdict(list)
        prog_index = f'site:{lang}/{t["prog"]}/index'

        for slug, p in pages.items():
            crumbs = p.get('breadcrumbs') or []
            if len(crumbs) >= 4:
                tslug, tlabel = crumbs[2]['slug'].rstrip('/').split('/')[-1], crumbs[2]['description']
            else:
                tslug, tlabel = t['other'], t['other'].capitalize()
            topics.setdefault(tslug, tlabel)
            sub = ' › '.join(c['description'] for c in crumbs[3:-1])
            title = p.get('title') or slug
            desc = (p.get('metaData') or {}).get('metaDescription') or ''
            meta_base = OrderedDict(
                topic=' › '.join(c['description'] for c in crumbs[1:-1]),
                source=f'{SOURCE}{"/en/information" if lang == "en" else "/informatie"}/{slug}',
                last_modified=((p.get('metaData') or {}).get('lastModified') or p.get('publicationDateTime') or '')[:10],
            )
            for l2 in (p.get('metaData') or {}).get('languages') or []:
                m = re.match(r'^/(?:en/information|informatie)/(.+)$', l2.get('slug') or '')
                ol = (l2.get('language') or '').lower()
                if m and ol in self.pages and m.group(1) in self.pages[ol]:
                    meta_base['translation'] = self.url(f'{ol}/{T[ol]["info"]}/{m.group(1)}', 'md')

            content = {k: p.get(k) for k in CONTENT_KEYS}
            gen = filt(content, None)
            gen_key = json.dumps(gen, sort_keys=True)
            page_studies = [s['value'] for s in p.get('resolvedStudies') or [] if s['value'] != ALL and s['value'] in studies]
            groups = OrderedDict()  # key -> [studies]
            for s in page_studies:
                f = filt(content, s); k = json.dumps(f, sort_keys=True)
                groups.setdefault(k, (f, []))[1].append(s)
            base_path = f'{lang}/{t["info"]}/{slug}'
            target = {}
            variants = []
            fallback_count = defaultdict(int)
            # If the page differs per programme, every programme gets a full version file (also those that
            # see only the general content): the general page then shows just the intro and the versions.
            varies = any(k != gen_key for k in groups)
            for k, (f, ss) in groups.items():
                if not varies:
                    for s in ss: target[s] = (base_path, False)
                    continue
                name, vlabel = self.tax.variant_name(ss, fallback_count)
                vpath = f'{base_path}/{name}'
                variants.append((vpath, ss))
                for s in ss: target[s] = (vpath, k != gen_key)
                labels = ', '.join(studies[s] for s in ss)
                body = f'<p><strong>{t["applies"]}:</strong> {e(labels)}.</p>\n' + content_html(f, t)
                self.write(lang, vpath, f'{title} – {vlabel or studies[ss[0]] + (f" (+{len(ss) - 1})" if len(ss) > 1 else "")}',
                           body, OrderedDict(meta_base, general_version=self.url(base_path, 'md')), desc)

            # general page: only the intro and the versions per programme, so agents read the right version
            if variants:
                note = t['generic_note'].format(link=f'<a href="{prog_index}">{t["programmes"]}</a>')
                intro = p.get('introductionText') or desc
                lst = ''.join(f'<li><a href="site:{vp}">{e(", ".join(studies[s] for s in ss))}</a></li>' for vp, ss in variants)
                body = (f'<p><em>{note}</em></p>\n' + (f'<p>{e(intro)}</p>\n' if intro else '')
                        + f'<h2>{t["more_info"]}</h2>\n<ul>{lst}</ul>')
            else:
                body = f'<p><em>{t["only_general"]}</em></p>\n' + content_html(gen, t)
            self.write(lang, base_path, title, body, meta_base, desc)
            generic_by_topic[tslug].append((sub, title, desc, base_path, bool(variants)))
            for s in page_studies:
                by_study[s].append((tslug, sub, title, desc) + target[s])

        # topic pages (general) and the language index
        for tslug, tlabel in topics.items():
            body = f'<p>{t["generic_topic_intro"].format(topic=e(tlabel), link=f"<a href={chr(34)}{prog_index}{chr(34)}>{t["programmes"]}</a>")}</p>\n'
            body += self.page_list(generic_by_topic[tslug], t, specific_label=t['with_specific'])
            self.write(lang, f'{lang}/{t["topics"]}/{tslug}', tlabel, body)
        idx = f'<p>{t["prog_intro"]}</p>\n<p><a href="{prog_index}">{t["programmes"]}</a></p>\n<h2>{t["topics_title"]}</h2>\n<ul>' + ''.join(
            f'<li><a href="site:{lang}/{t["topics"]}/{ts}">{e(tl)}</a> ({len(generic_by_topic[ts])} {t["pages"]})</li>' for ts, tl in topics.items()) + '</ul>'
        self.write(lang, f'{lang}/index', t['site_title'], idx)

        # programme indexes
        lst = ''.join(f'<li><a href="site:{lang}/{t["prog"]}/{s}/index">{e(l)}</a></li>' for s, l in studies.items() if by_study[s])
        self.write(lang, f'{lang}/{t["prog"]}/index', t['programmes'], f'<p>{t["prog_intro"]}</p>\n<ul>{lst}</ul>')
        for s, label in studies.items():
            entries = by_study[s]
            if not entries: continue
            per_topic = defaultdict(list)
            for tslug, sub, title, desc, path, spec in entries: per_topic[tslug].append((sub, title, desc, path, spec))
            body = f'<p>{t["study_intro"].format(label=e(label))}</p>\n<ul>' + ''.join(
                f'<li><a href="site:{lang}/{t["prog"]}/{s}/{ts}">{e(tl)}</a> ({len(per_topic[ts])} {t["pages"]}, '
                f'{sum(x[4] for x in per_topic[ts])} {t["with_specific"]})</li>'
                for ts, tl in topics.items() if per_topic[ts]) + '</ul>'
            self.write(lang, f'{lang}/{t["prog"]}/{s}/index', label, body)
            for ts, tl in topics.items():
                if not per_topic[ts]: continue
                body = f'<p>{t["topic_intro"].format(topic=e(tl), label=e(label))}</p>\n' + self.page_list(per_topic[ts], t, specific_label=t['specific'])
                self.write(lang, f'{lang}/{t["prog"]}/{s}/{ts}', f'{label}: {tl}', body)
        return dict(pages=len(pages), studies=len(studies), topics=list(topics.values()))

    @staticmethod
    def page_list(entries, t, specific_label):
        by_sub = OrderedDict()
        for sub, title, desc, path, spec in sorted(entries, key=lambda x: (x[0], x[1].lower())):
            by_sub.setdefault(sub, []).append((title, desc, path, spec))
        h = ''
        for sub, items in by_sub.items():
            if sub: h += f'<h2>{e(sub)}</h2>\n'
            h += '<ul>' + ''.join(
                f'<li><a href="site:{path}">{e(title)}</a>{" (" + specific_label + ")" if spec else ""}{": " + e(short(desc)) if desc else ""}</li>'
                for title, desc, path, spec in items) + '</ul>\n'
        return h

    def write_root(self, summary):
        u = lambda p: self.url(p, 'md')
        txt = f"""# student.uva.nl voor AI-agents / for AI agents

> Informatie voor studenten van de Universiteit van Amsterdam (UvA), van student.uva.nl, als Markdown en simpele HTML.
> Veel informatie verschilt per opleiding. Kies daarom eerst de opleiding van de student en volg de links vanaf de index van die opleiding.
> Information for students of the University of Amsterdam. Much of it differs per programme: choose the student's programme first.

Experimentele versie, gemaakt op {self.date}. Bij twijfel geldt {SOURCE}.

## Nederlands

- [Opleidingen]({u('nl/opleidingen/index')}): kies een opleiding; de index van die opleiding linkt per onderwerp naar de juiste versie van elke pagina.
- [Onderwerpen]({u('nl/index')}): de algemene versies per onderwerp.
- Elke pagina bestaat als .md en als .html. Algemene versie: {self.base}/nl/informatie/<slug>.md, met onderaan de links naar de versies per opleiding.

## English

- [Programmes]({u('en/programmes/index')}): choose a programme; its index links to the right version of every page, by topic.
- [Topics]({u('en/index')}): the general versions by topic.
- Every page exists as .md and .html. General version: {self.base}/en/information/<slug>.md, with links to the versions per programme at the end.
"""
        open(os.path.join(self.out, 'llms.txt'), 'w').write(txt)
        open(os.path.join(self.out, 'index.md'), 'w').write(txt)
        idx = (f'<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
               f'<title>student.uva.nl voor AI-agents</title><link rel="alternate" type="text/markdown" href="{e(self.base)}/llms.txt"></head>'
               f'<body style="font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;background:#fff;color:#222">'
               f'<h1>student.uva.nl voor AI-agents</h1><p>Zie <a href="{e(self.base)}/llms.txt">llms.txt</a>.</p><ul>'
               f'<li><a href="{e(self.url("nl/opleidingen/index", "html"))}">Opleidingen</a> · <a href="{e(self.url("nl/index", "html"))}">Onderwerpen</a></li>'
               f'<li><a href="{e(self.url("en/programmes/index", "html"))}">Programmes</a> · <a href="{e(self.url("en/index", "html"))}">Topics</a></li></ul></body></html>')
        open(os.path.join(self.out, 'index.html'), 'w').write(idx)
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(
            f'<url><loc>{html.escape(x)}</loc></url>\n' for x in self.html_urls) + '</urlset>\n'
        open(os.path.join(self.out, 'sitemap.xml'), 'w').write(sm)
        open(os.path.join(self.out, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\n\nSitemap: {self.base}/sitemap.xml\n')
        open(os.path.join(self.out, '.nojekyll'), 'w').write('')


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=os.path.join(here, '..', 'data'))
    ap.add_argument('--out', default=os.path.join(here, '..', 'site'))
    ap.add_argument('--base-url', default='http://localhost:8000')
    a = ap.parse_args()
    site = Site(a.data, a.out, a.base_url)
    summary = site.build()
    for lang, s in summary.items():
        print(f'{lang}: {s["pages"]} pages, {s["studies"]} programmes, {len(s["topics"])} topics')
    print(f'{site.files} files, {site.bytes / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
