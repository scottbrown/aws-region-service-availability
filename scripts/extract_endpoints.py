#!/usr/bin/env python3
"""Extract per-endpoint-type region availability from an AWS GR service page.

Reads a service endpoints HTML page (the docs.aws.amazon.com/general/latest/gr/<svc>.html
family) and emits compact JSON:

  {
    "slug": "ses.html",
    "title": "Amazon Simple Email Service ...",
    "sections": [
       {"id": "ses_region", "title": "Service API endpoints",
        "region_codes": ["us-east-1", ...], "region_names": [...], "kind": "endpoint"},
       {"id": "ses_inbound_endpoints", "title": "Email Receiving endpoints", ...},
       ...
    ],
    "notes": ["Amazon SES does not support email receiving in ... us-gov-west-1, us-gov-east-1"]
  }

It is deliberately conservative: it classifies each <h2 id=...> section + following table,
pulls any AWS region code (regex) found in that table, and captures "not available/supported"
prose notes. Region-code detection is layout-independent, which is what makes this robust
across the inconsistent page templates.
"""
import sys, re, json
from html.parser import HTMLParser

REGION_RE = re.compile(r'\b((?:us|eu|ap|ca|sa|af|me|il|mx|us-gov|eusc)-[a-z]+-\d)\b')

class Doc(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self._in_title = False
        # event stream of ('h2', id, text) and ('table_text', text) and ('note', text)
        self.events = []
        self._cur_h2_id = None
        self._cur_h2_text = []
        self._in_h2 = False
        self._in_table = False
        self._table_text = []
        self._in_note = False        # awsui/note callout
        self._note_depth = 0
        self._note_text = []
        self._capture_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'h1' and self.title is None:
            self._capture_title = True
        if tag in ('h2', 'h3'):
            self._in_h2 = True
            self._cur_h2_id = a.get('id')
            self._cur_h2_text = []
        if tag == 'table':
            self._in_table = True
            self._table_text = []
        cls = a.get('class', '') or ''
        if ('note' in cls or 'awsui_alert' in cls) and not self._in_note:
            self._in_note = True
            self._note_depth = 1
            self._note_text = []
        elif self._in_note:
            self._note_depth += 1

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3') and self._in_h2:
            self._in_h2 = False
            self.events.append(('h2', self._cur_h2_id, ' '.join(''.join(self._cur_h2_text).split())))
        if tag == 'table' and self._in_table:
            self._in_table = False
            self.events.append(('table', ''.join(self._table_text)))
        if tag == 'h1':
            self._capture_title = False
        if self._in_note:
            self._note_depth -= 1
            if self._note_depth <= 0:
                self._in_note = False
                txt = ' '.join(''.join(self._note_text).split())
                if txt:
                    self.events.append(('note', txt))

    def handle_data(self, data):
        if self._capture_title:
            if self.title is None: self.title = ''
            self.title += data
        if self._in_h2:
            self._cur_h2_text.append(data)
        if self._in_table:
            self._table_text.append(data + ' ')
        if self._in_note:
            self._note_text.append(data)


def parse(slug, html):
    d = Doc()
    d.feed(html)
    sections = []
    # pair each h2 with the next table that follows it
    pending_h2 = None
    notes = []
    for ev in d.events:
        if ev[0] == 'h2':
            pending_h2 = {'id': ev[1], 'title': ev[2]}
        elif ev[0] == 'note':
            notes.append(ev[1])
        elif ev[0] == 'table':
            codes = []
            for m in REGION_RE.findall(ev[1]):
                if m not in codes:
                    codes.append(m)
            if pending_h2 is not None:
                sec = dict(pending_h2)
            else:
                sec = {'id': None, 'title': '(table)'}
            sec['region_codes'] = sorted(codes)
            sec['region_count'] = len(codes)
            # heuristic kind: endpoint-ish if it has region codes and title hints
            t = (sec['title'] or '').lower()
            if codes and not any(k in t for k in ('quota', 'limit', 'ip range', 'ip ranges')):
                sec['kind'] = 'availability'
            else:
                sec['kind'] = 'other'
            sections.append(sec)
            pending_h2 = None
    # also scan notes for region codes mentioned as unavailable
    note_objs = []
    for n in notes:
        ncodes = sorted(set(REGION_RE.findall(n)))
        neg = bool(re.search(r'not (currently )?(available|support)', n, re.I)) or 'does not support' in n.lower()
        note_objs.append({'text': n[:400], 'region_codes': ncodes, 'negative': neg})
    return {
        'slug': slug,
        'title': (d.title or '').strip(),
        'sections': [s for s in sections if s['kind'] == 'availability'],
        'notes': note_objs,
    }


if __name__ == '__main__':
    slug = sys.argv[1] if len(sys.argv) > 1 else '(stdin)'
    html = sys.stdin.read()
    print(json.dumps(parse(slug, html), indent=2))
