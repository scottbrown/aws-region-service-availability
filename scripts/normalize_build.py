#!/usr/bin/env python3
"""Deterministic normalizer + builder (no LLM).

Reads  build/endpoints-extracted.jsonl  (from extract_endpoints.py)
       scripts/region-meta.json
Writes site/aws-availability.json   (the dataset the page consumes)

Logic (deterministic reproduction of what the original multi-agent pass did):
  - one endpoint type per *titled* availability section (type = section title)
  - untitled "(table)" sections are FIPS/continuation tables: their regions count
    toward the service's union but do NOT create a distinct (partial-causing) type
  - prose-note exclusions: resolve region NAMES in a negative note to codes, match
    the note to the right endpoint type by title-keyword overlap, remove those codes
    from that type and record them under excludedByNote
  - scope: unknown (no sections) / global (single endpoint, <=1 region) / regional
  - per-region status: full (all endpoint types) / partial (some)
"""
import json, re, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.environ.get('BUILD_DIR', os.path.join(ROOT, 'build'))
EXTRACT = os.path.join(BUILD, 'endpoints-extracted.jsonl')
META = os.path.join(ROOT, 'scripts', 'region-meta.json')
OUT = os.path.join(ROOT, 'site', 'aws-availability.json')

CONT_ORDER = ['North America', 'South America', 'Europe', 'Middle East', 'Africa', 'Asia Pacific', 'Other']
STOP = {'endpoints', 'endpoint', 'service', 'services', 'and', 'quotas', 'the', 'for', 'aws', 'amazon',
        'region', 'regions', 'api', 'used', 'by', 'open', 'click', 'links', 'http', 'https', 'of', 'a'}


def load_meta():
    with open(META) as f:
        return json.load(f)


def name_to_code_pairs(meta):
    # longest names first so "AWS GovCloud (US-East)" matches before "US-East"
    return sorted(((m['name'], code) for code, m in meta.items()), key=lambda p: -len(p[0]))


def resolve_names_in_note(text, name_pairs):
    found = []
    for name, code in name_pairs:
        if name and name in text and code not in found:
            found.append(code)
    return found


def title_tokens(title):
    toks = re.findall(r'[a-z0-9]+', (title or '').lower())
    return {t for t in toks if t not in STOP and len(t) > 1}


def note_matches_section(note_text, section_title):
    lead = re.split(r'\b(?:is|are)\b', note_text, maxsplit=1)[0].lower()
    sect_toks = title_tokens(section_title)
    if not sect_toks:
        return False
    return any(t in lead for t in sect_toks)


def build():
    meta = load_meta()
    valid = set(meta.keys())
    name_pairs = name_to_code_pairs(meta)

    services = []
    with open(EXTRACT) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            sections = rec.get('sections') or []
            notes = rec.get('notes') or []
            neg_notes = [n for n in notes if n.get('negative')]

            ets = []
            anon_regions = set()
            for sec in sections:
                regions = sorted({c for c in (sec.get('region_codes') or []) if c in valid})
                title = (sec.get('title') or '').strip()
                if not sec.get('id') and (title == '' or title == '(table)'):
                    anon_regions |= set(regions)
                    continue
                excluded = []
                for n in neg_notes:
                    codes = resolve_names_in_note(n.get('text', ''), name_pairs)
                    if codes and note_matches_section(n.get('text', ''), title):
                        for c in codes:
                            if c in regions:
                                regions.remove(c)
                            if c not in excluded:
                                excluded.append(c)
                ets.append({
                    'type': title or 'API',
                    'sectionId': sec.get('id'),
                    'regions': regions,
                    'regionCount': len(regions),
                    'excludedByNote': sorted(set(excluded)),
                })
            if anon_regions:
                if ets:
                    merged = sorted(set(ets[0]['regions']) | anon_regions)
                    ets[0]['regions'] = merged
                    ets[0]['regionCount'] = len(merged)
                else:
                    ets.append({'type': 'API', 'sectionId': None,
                                'regions': sorted(anon_regions), 'regionCount': len(anon_regions),
                                'excludedByNote': []})

            title = rec.get('title', '')
            if not ets:
                scope = 'unknown'
            elif len(ets) == 1 and ets[0]['regionCount'] <= 1:
                scope = 'global'
            else:
                scope = 'regional'

            union = set()
            for et in ets:
                union |= set(et['regions'])
            active_types = [e for e in ets if e['regions']]
            total = len(active_types) or 1
            region_status = {}
            for r in sorted(union):
                present = sum(1 for e in ets if r in e['regions'])
                region_status[r] = 'full' if present >= total else 'partial'

            services.append({
                'slug': rec.get('slug'),
                'name': re.sub(r'\s+endpoints and quotas$', '', title).strip() or rec.get('slug'),
                'scope': scope,
                'regions': sorted(union),
                'regionCount': len(union),
                'endpointTypeCount': len(ets),
                'endpointTypes': ets,
                'regionStatus': region_status,
            })

    services.sort(key=lambda x: x['name'].lower())

    seen = set()
    for s in services:
        seen |= set(s['regions'])
    regions = []
    for code in sorted(seen, key=lambda c: (CONT_ORDER.index(meta.get(c, {}).get('continent', 'Other')), c)):
        m = meta.get(code, {})
        regions.append({
            'code': code, 'name': m.get('name', code),
            'continent': m.get('continent', 'Other'), 'partition': m.get('partition', 'aws'),
            'serviceCount': sum(1 for s in services if code in s['regions']),
        })

    partial_cells = sum(1 for s in services for st in s['regionStatus'].values() if st == 'partial')
    multi = sum(1 for s in services if s['endpointTypeCount'] > 1)

    out = {
        'metadata': {
            'docsPage': 'https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html',
            'source': 'Per-service endpoint pages (docs.aws.amazon.com/general/latest/gr/<service>.html), normalized per endpoint type',
            'serviceCount': len(services), 'regionCount': len(regions),
            'multiEndpointTypeServices': multi, 'partialAvailabilityCells': partial_cells,
            'note': 'A region is "full" if every endpoint type is offered there, "partial" if only some (e.g. SES API present but Inbound/SMTP absent in ca-west-1).',
        },
        'regions': regions, 'services': services,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"services={len(services)} regions={len(regions)} multiType={multi} partialCells={partial_cells} -> {OUT}")


if __name__ == '__main__':
    build()
