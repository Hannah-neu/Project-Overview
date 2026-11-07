import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import webbrowser

import pymupdf

ROOT = Path(__file__).resolve().parent
MAX_FILE = 60 * 1024 * 1024

def norm(text):
    return re.sub(r'\s+', ' ', text).lower()

def visual(page, rect):
    return pymupdf.Rect(rect) * page.rotation_matrix

def nearest_value(page, label, choices):
    hits = page.search_for(label)
    if not hits:
        return None
    anchor = visual(page, hits[0])
    candidates = []
    for word in page.get_text('words'):
        value = word[4].strip(' :/()').upper()
        if value not in choices:
            continue
        box = visual(page, word[:4])
        dx = box.x0 - anchor.x1
        dy = abs((box.y0 + box.y1 - anchor.y0 - anchor.y1) / 2)
        if -3 <= dx <= page.rect.width * .22 and dy <= max(12, anchor.height):
            candidates.append((dx + dy * 3, value))
    return min(candidates)[1] if candidates else None

def label_color(page):
    hits = page.search_for('QGCx oneQ result')
    if not hits:
        return None
    anchor = visual(page, hits[0])
    candidates = []
    for drawing in page.get_drawings():
        fill = drawing.get('fill')
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[:3]
        color = 'red' if r > .6 and g < .45 and b < .45 else 'yellow' if r > .7 and g > .55 and b < .5 else 'green' if g > .4 and g > r * 1.25 and g > b * 1.15 else None
        if not color:
            continue
        box = visual(page, drawing['rect'])
        dx = box.x0 - anchor.x1
        dy = abs((box.y0 + box.y1 - anchor.y0 - anchor.y1) / 2)
        if -5 <= dx <= page.rect.width * .18 and dy <= max(12, anchor.height):
            candidates.append((max(0, dx) + dy * 3, color))
    return min(candidates)[1] if candidates else None

def three_block_color(page):
    """Find the top color in a unique vertical three-cell PRC rating stack.

    Restrict detection to the project-name / component boundary and require
    similar, adjacent cells in the same column. Nearby time/profit labels help
    distinguish this column from other KPI color blocks. Ambiguity is review.
    """
    from itertools import combinations
    names = page.search_for('Project Name/Description')
    components = page.search_for('Component Name')
    if not names or not components:
        return None
    name_box = visual(page, names[0])
    component_box = visual(page, components[0])
    upper = max(0, name_box.y0 - max(8, name_box.height))
    lower = component_box.y0
    if lower <= upper:
        return None
    cells = []
    for drawing in page.get_drawings():
        fill = drawing.get('fill')
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[:3]
        color = ('red' if r > .6 and g < .45 and b < .45 else
                 'yellow' if r > .7 and g > .55 and b < .5 else
                 'green' if g > .4 and g > r * 1.25 and g > b * 1.15 else None)
        if not color:
            continue
        box = visual(page, drawing['rect'])
        if not (page.rect.width * .45 <= box.x0 and box.x1 <= page.rect.width and
                upper <= box.y0 and box.y1 <= lower and
                page.rect.width * .008 <= box.width <= page.rect.width * .12 and
                page.rect.height * .004 <= box.height <= page.rect.height * .07):
            continue
        if not any(color == other_color and all(abs(x-y) < 1 for x,y in zip(box, other_box)) for other_color,other_box in cells):
            cells.append((color, box))
    stacks = []
    for triple in combinations(cells, 3):
        triple = sorted(triple, key=lambda item:item[1].y0)
        boxes = [item[1] for item in triple]
        width = boxes[0].width
        if any(abs((b.x0+b.x1)/2-(boxes[0].x0+boxes[0].x1)/2)>max(2,width*.2) or not .7<=b.width/width<=1.35 for b in boxes[1:]):
            continue
        if any(not .55<=b.height/boxes[0].height<=1.8 for b in boxes[1:]):
            continue
        if any(not -2<=boxes[i+1].y0-boxes[i].y1<=max(8,boxes[i].height*.5) for i in (0,1)):
            continue
        stacks.append(triple)
    if not stacks:
        return None
    def matches_label(box, label):
        for hit in page.search_for(label):
            anchor = visual(page, hit)
            cy = (anchor.y0+anchor.y1)/2
            if box.y0-3 <= cy <= box.y1+3 and -5 <= box.x0-anchor.x1 <= page.rect.width*.1:
                return True
        return False
    identified = [triple for triple in stacks if matches_label(triple[1][1], 'On Time') and matches_label(triple[2][1], 'On Profit')]
    chosen = identified if identified else stacks
    return chosen[0][0][0] if len(chosen) == 1 else None

def has_superopl_color(page):
    # Render the upper-left corner so both embedded-image and vector logos work.
    clip = pymupdf.Rect(0, 0, page.rect.width * .4, page.rect.height * .16)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, colorspace=pymupdf.csRGB, alpha=False)
    data = pix.samples
    count = 0
    for i in range(0, len(data), 3):
        r, g, b = data[i:i+3]
        if r > 110 and b > 60 and r > g * 1.35 and b > g * 1.2:
            count += 1
    return count >= 30

def analyze(data):
    doc = pymupdf.open(stream=data, filetype='pdf')
    if doc.needs_pass:
        raise ValueError('The PDF is encrypted. Remove password protection before checking.')
    if len(doc) > 500:
        raise ValueError('The PDF exceeds 500 pages. Split it before checking.')
    texts = [norm(p.get_text()) for p in doc]
    def pages(*terms):
        return [i + 1 for i,t in enumerate(texts) if all(term in t for term in terms)]
    def titles(title):
        found = []
        for i, page in enumerate(doc):
            for hit in page.search_for(title):
                box = visual(page, hit)
                if box.x0 < page.rect.width * .5 and box.y0 < page.rect.height * .25:
                    found.append(i + 1)
                    break
        return found
    prcs = pages('project summary', 'basic data', 'system/components', 'milestone', 'customer')
    specs = [
        ('Project time schedule', pages('milestones','product development','task name')),
        ('R&D Sheet', titles('R&D Sheet')),
        ('Profitability data with history', [i+1 for i,t in enumerate(texts) if ('profitiability data with history' in t or 'profitability data with history' in t) and 'profitability data' in t]),
        ('Decision sheet', titles('Decision minutes')),
        ('Effort Tracking', titles('Effort Tracking')),
        ('oneQ cover page', pages('assessment cover sheet','project data','assessment results')),
        ('System assessment (diagram, tracking of critical points, signature page)', [n for n in pages('system assessment') if n not in prcs]),
        ('Risk management report', titles('Risk Report')),
    ]
    results = []
    def add(name,status,detail,pages_=None):
        results.append(dict(name=name,status=status,detail=detail,pages=pages_ or []))
    add('PRC / Project Summary','pass' if prcs else 'review','PRC identified; standard document checks are enabled.' if prcs else 'PRC not identified. Confirm manually whether the standard document checks apply.',prcs)
    if not prcs:
        return dict(total=len(doc),results=results, textless=[i+1 for i,t in enumerate(texts) if len(t)<30])
    for name,found in specs:
        if name == 'Project time schedule' and not found:
            add(name,'missing','Project time schedule not found. Use the MS Project time schedule.')
            continue
        if name == 'Risk management report' and found:
            verified = [n for n in found if has_superopl_color(doc[n-1])]
            if not verified:
                add(name,'review','Risk Report title found, but the magenta logo at the upper left could not be identified. Review manually.',found)
            else:
                add(name,'pass','Risk Report title and magenta logo at the upper left found.',verified)
            continue
        add(name,'pass' if found else 'missing','A matching page was found.' if found else 'No page matched all features. Check for missing documents or review manually.',found)
    corrective = pages('corrective actions of last decision sheet')
    decisions = titles('Decision minutes')
    pmp_pages = [i + 1 for i, text in enumerate(texts) if len(re.findall(r'\bproject\s+management\s+plan\b', text)) > 2]
    if corrective:
        add('Last decision minutes','pass' if len(decisions)>=2 else 'missing',f'A corrective-actions page was found (page(s) {", ".join(map(str,corrective))}). At least 2 Decision minutes pages are required; {len(decisions)} found.', decisions)
    else:
        add('Last decision minutes','na','No previous corrective-actions page was found; this check does not apply.')
    for n in prcs:
        p = doc[n-1]
        apic = nearest_value(p,'APIC',set('ABCDE')) or nearest_value(p,'PIC',set('ABCDE'))
        if apic == 'E':
            add('PMP / APIC','na','APIC is E; no additional PMP reminder is required.',[n])
        elif apic and pmp_pages:
            add('PMP / APIC','pass',f'APIC is {apic}; Project Management Plan appears more than twice on a page, indicating that PMP material was provided.',pmp_pages)
        elif apic:
            add('PMP / APIC','review',f'APIC is {apic}; PMP material is required. No page contains Project Management Plan more than twice; provide it or verify manually.',[n])
        else:
            add('PMP / APIC','review','APIC / PIC could not be read reliably. Confirm manually whether PMP is required.',[n])
        color = label_color(p)
        color_source = 'label' if color else None
        if color is None:
            color = three_block_color(p)
            if color:
                color_source = 'first of three color blocks'
        covers = specs[5][1]
        if len(covers)!=1:
            add('oneQ rating consistency','review','A unique oneQ cover page was not found. Confirm the correspondence manually.',[n]+covers)
            continue
        text = texts[covers[0]-1]
        section = text.split('assessment results',1)[1].split('result of previous assessments',1)[0]
        labels = ['project management','requirement management','product development','preparation for production','preparation for series operation']
        values = []
        for label in labels:
            match = re.search(re.escape(label) + r'\s+(red|yellow|green)\b', section)
            if match:
                values.append(match.group(1))
        expected = ('red' if 'red' in values else 'yellow' if 'yellow' in values else 'green') if len(values) == len(labels) else None
        overall_match = re.search(r'overall rating\s+(red|yellow|green)\b', section)
        overall = overall_match.group(1) if overall_match else None
        if not color or not expected or not overall:
            add('oneQ rating consistency','review',f'The color or current rating could not be reliably identified (PRC: {color or "unidentified"}; oneQ: {expected or "unidentified"}). Review manually.',[n,covers[0]])
        else:
            consistent = color == expected == overall
            add('oneQ rating consistency','pass' if consistent else 'missing',f'PRC: {color} (source: {color_source}); oneQ Overall rating: {overall}; the current assessments yield {expected} using red > yellow > green. '+('Ratings are consistent.' if consistent else 'Ratings differ; please review.'),[n,covers[0]])
    return dict(total=len(doc),results=results,textless=[i+1 for i,t in enumerate(texts) if len(t)<30])
