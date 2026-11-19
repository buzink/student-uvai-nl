"""Measure per-study variants and sizes of informatie pages. Usage: python3 -I measure.py <pages_dir> <out_json>"""
import json, glob, re, sys, hashlib, statistics, collections, html, os

SKIP = {'id', 'contentId', 'languageId', 'projectId', '__typename', 'url', 'slug', 'value', 'studies',
        'publicationDateTime', 'lastModified', 'openGraphImageUrl', 'codename', 'collection', 'language',
        'resolvedStudies', 'relatedContent', 'relatedTopicContent', 'metaData', 'resolvedFilteredTopics',
        'resolvedTopics', 'resolvedHeroImage', 'umbrellaPageInfo', 'breadcrumbs'}
ALL = 'alle_opleidingen'

def filt(o, study):
    """Keep what a student of `study` would see (study=None: default view)."""
    if isinstance(o, dict):
        st = o.get('studies')
        if isinstance(st, list) and st:
            if ALL not in st and (study is None or study not in st):
                return None
        return {k: filt(v, study) for k, v in o.items()}
    if isinstance(o, list):
        return [x for x in (filt(v, study) for v in o) if x is not None]
    return o

def text(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in SKIP or 'image' in k.lower(): continue
            text(v, out)
    elif isinstance(o, list):
        for v in o: text(v, out)
    elif isinstance(o, str) and o.strip():
        t = html.unescape(re.sub(r'<[^>]+>', ' ', o))
        out.append(re.sub(r'\s+', ' ', t).strip())
    return out

def render(o):
    return '\n'.join(text(o, []))

pages = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.json'))):
    d = json.load(open(f)); p = d['page']
    if not p: continue
    studies = [s['value'] for s in (p.get('resolvedStudies') or []) if s['value'] != ALL]
    generic = render(filt(p, None))
    allc = render(p)
    var = {}
    sizes = []
    specific = 0
    for s in studies:
        t = render(filt(p, s))
        h = hashlib.md5(t.encode()).hexdigest()
        var.setdefault(h, len(t)); sizes.append(len(t))
        if t != generic: specific += 1
    pages.append(dict(lang=d['lang'], slug=d['slug'], n_studies=len(studies), generic=len(generic), all=len(allc),
                      variants=len(var), specific=specific, var_chars=sum(var.values()),
                      med=statistics.median(sizes) if sizes else len(generic), mx=max(sizes) if sizes else len(generic),
                      crumbs=[b['description'] for b in (p.get('breadcrumbs') or [])][1:-1]))
json.dump(pages, open(sys.argv[2], 'w'), indent=1)
print('pages', len(pages))
