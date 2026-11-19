"""Download the ?allcontent data of all information pages of student.uva.nl.

Uses the Next.js data route (/_next/data/<buildId>/<lang>/information/<slug>.json?allcontent),
which returns the same data as the page itself, without the HTML.

Usage: python3 fetch.py [--out data] [--refresh]
"""
import argparse, concurrent.futures as cf, json, os, re, urllib.request

SITE = 'https://student.uva.nl'
TAXONOMY = 'https://deliver.kontent.ai/2a7f7854-b38e-015d-c63a-62b2c8fa2017/taxonomies/study_programmes'
UA = {'User-Agent': 'Mozilla/5.0 (student-uvai-nl generator)'}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'data'))
    ap.add_argument('--refresh', action='store_true', help='download pages again even if cached')
    a = ap.parse_args()
    pages_dir = os.path.join(a.out, 'pages'); os.makedirs(pages_dir, exist_ok=True)

    home = get(SITE + '/')
    build = re.search(r'"buildId":"([^"]+)"', home).group(1)
    sitemap = get(SITE + '/sitemap.xml')
    open(os.path.join(a.out, 'sitemap.xml'), 'w').write(sitemap)
    # The study_programmes taxonomy (public Delivery API): its intermediate levels name the variant files.
    open(os.path.join(a.out, 'taxonomy_study_programmes.json'), 'w').write(get(TAXONOMY))

    jobs = []
    for p in re.findall(r'<loc>https://student\.uva\.nl([^<]*)', sitemap):
        m = re.match(r'^/informatie/(.+)$', p) or re.match(r'^/en/information/(.+)$', p)
        if m: jobs.append(('en' if p.startswith('/en/') else 'nl', m.group(1)))

    def fetch(job):
        lang, slug = job
        fn = os.path.join(pages_dir, f'{lang}__{slug.replace("/", "__")}.json')
        if os.path.exists(fn) and not a.refresh: return 'cached'
        try:
            d = json.loads(get(f'{SITE}/_next/data/{build}/{lang}/information/{slug}.json?allcontent'))
            data = d['pageProps']['dehydratedState']['queries'][0]['state']['data']
            json.dump({'lang': lang, 'slug': slug, 'page': data.get('informationPage')}, open(fn, 'w'))
            return 'ok'
        except Exception as e:  # noqa: BLE001 - report and continue
            return f'error {lang}/{slug}: {e}'

    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(fetch, jobs))
    errors = [r for r in res if r.startswith('error')]
    print(f'{len(jobs)} pages, {sum(r == "ok" for r in res)} downloaded, {sum(r == "cached" for r in res)} cached, {len(errors)} errors')
    for e in errors: print(e)


if __name__ == '__main__':
    main()
