"""Fetch ?allcontent page data for all informatie/information pages via the Next.js data route.
Stores only the informationPage object per page. Usage: python3 -I fetch_info.py <dl_dir> <buildId>"""
import json, os, re, sys, urllib.request, concurrent.futures as cf

dl, build = sys.argv[1], sys.argv[2]
out = os.path.join(dl, 'pages'); os.makedirs(out, exist_ok=True)
locs = re.findall(r'<loc>https://student\.uva\.nl([^<]*)', open(os.path.join(dl, 'sitemap.xml')).read())
jobs = []
for p in locs:
    m = re.match(r'^/informatie/(.+)$', p)
    if m: jobs.append(('nl', m.group(1)))
    m = re.match(r'^/en/information/(.+)$', p)
    if m: jobs.append(('en', m.group(1)))

def get(job):
    lang, slug = job
    fn = os.path.join(out, f'{lang}__{slug.replace("/", "__")}.json')
    if os.path.exists(fn): return 'cached'
    url = f'https://student.uva.nl/_next/data/{build}/{lang}/information/{slug}.json?allcontent'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (measurement script)'})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=60))
        data = d['pageProps']['dehydratedState']['queries'][0]['state']['data']
        json.dump({'lang': lang, 'slug': slug, 'page': data.get('informationPage')}, open(fn, 'w'))
        return 'ok'
    except Exception as e:
        return f'err {slug}: {e}'

with cf.ThreadPoolExecutor(6) as ex:
    res = list(ex.map(get, jobs))
from collections import Counter
print(len(jobs), Counter(r.split(' ')[0] for r in res))
for r in res:
    if r.startswith('err'): print(r)
