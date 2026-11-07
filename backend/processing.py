"""Read saved Excel values and reproduce the two Power Query table shapes."""
from __future__ import annotations
import csv
import io
import re
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

FIELDS = ['No','PRJ MCR-ID','PRJ name','Customer','P-ID','Acq manager','Project manager','Engine Segment\n (groups)','Prod Category','Emission','(A)PIC','A/K Project  ','System ','Components','New released components','injector','Pump','Rail','ECU','DNOX','Other Component','PRJ Status','SE2 plan','SE3 plan','SE4 plan','QGC0 plan','QGC4 plan','SE2 Act','SE3 Act','SE4 Act','QGC0 Act','QGC4 Act','B sample','C sample','D sample']
PLAN = ['SE2 plan','SE3 plan','SE4 plan','QGC0 plan','QGC4 plan']
ACTUAL = ['SE2 Act','SE3 Act','SE4 Act','QGC0 Act','QGC4 Act']
KEEP = set(FIELDS) - set(PLAN + ['QGC4 Act'])
COMPONENTS = {'injector':'injector','pump':'Pump','rail':'Rail','ECU':'ECU','DNOX':'DNOX','other':'Other Component'}

class ImportProblem(ValueError):
    pass

def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()

def date_value(value, epoch):
    if value is None or value == '': return None
    if isinstance(value, datetime): return value.date().isoformat()
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = from_excel(value, epoch)
            return parsed.date().isoformat() if isinstance(parsed, datetime) else None
        except (ValueError, OverflowError): return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d','%Y/%m/%d','%Y.%m.%d','%m/%d/%Y','%d/%m/%Y','%Y-%m-%d %H:%M:%S'):
        try: return datetime.strptime(text, fmt).date().isoformat()
        except ValueError: pass
    return None

def section(value):
    match = re.search(r'\(([^)]*)\)',str(value or ''))
    return match.group(1) if match else None

def scalar(value):
    if isinstance(value,(datetime,date,time)): return value.isoformat()
    return value

def process(filename: str, data: bytes):
    suffix = Path(filename).suffix.lower()
    issues = Counter(); epoch = None
    if suffix == '.xlsx':
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            epoch = wb.epoch
            if 'Sheet1' not in wb.sheetnames: raise ImportProblem('缺少工作表 Sheet1。')
            rows = list(wb['Sheet1'].iter_rows())
            if len(rows) < 2: raise ImportProblem('Sheet1 缺少第 2 行表头。')
            headers = [c.value for c in rows[1]]
            source = [[(None if c.data_type == 'e' else c.value) for c in row] for row in rows[2:]]
            for row in rows[2:]:
                for i,c in enumerate(row):
                    if c.data_type == 'e': issues[f'Excel error: {headers[i] if i < len(headers) else i+1}'] += 1
        except ImportProblem: raise
        except Exception as exc: raise ImportProblem(f'Excel 文件无法读取：{exc}') from exc
    elif suffix == '.csv':
        try:
            try: content = data.decode('utf-8-sig')
            except UnicodeDecodeError: content = data.decode('gb18030')
            all_rows = list(csv.reader(io.StringIO(content)))
            if not all_rows: raise ImportProblem('CSV 文件为空。')
            header_index = 0 if 'prj mcr-id' in [normalized(x) for x in all_rows[0]] else 1
            if len(all_rows) <= header_index: raise ImportProblem('CSV 文件缺少表头。')
            headers,source = all_rows[header_index],all_rows[header_index+1:]
            from openpyxl.utils.datetime import WINDOWS_EPOCH
            epoch = WINDOWS_EPOCH
        except ImportProblem: raise
        except (UnicodeError,csv.Error) as exc: raise ImportProblem(f'CSV 文件无法读取：{exc}') from exc
    else:
        raise ImportProblem('目前支持 .xlsx 和 .csv；旧版 .xls 暂不支持，请先另存为 .xlsx。')
    # Normalize only names, not values. Refuse ambiguous headers rather than silently choosing one.
    lookup = {}
    for i,h in enumerate(headers):
        if h is None or str(h).strip() == '': continue
        key = normalized(h)
        if key in lookup: raise ImportProblem(f'表头重复或标准化后冲突：{h}')
        lookup[key] = i
    missing = [x for x in FIELDS if normalized(x) not in lookup]
    if missing: raise ImportProblem('缺少必需字段：' + ', '.join(missing))
    mapping = {name:lookup[normalized(name)] for name in FIELDS}
    extras = [(str(h),i) for i,h in enumerate(headers) if h is not None and str(h).strip() and normalized(h) not in {normalized(x) for x in FIELDS}]
    projects=[]; milestones=[]
    for values in source:
        if not any(x is not None and x != '' for x in values): continue
        record = {name:(values[i] if i < len(values) else None) for name,i in mapping.items()}
        record['A Dept']=section(record['Acq manager']); record['K Dept']=section(record['Project manager'])
        projects.append({k:scalar(v) for k,v in record.items()})
        dates={}
        for name in PLAN+ACTUAL:
            dates[name]=date_value(record[name],epoch)
            if record[name] not in (None,'') and dates[name] is None: issues['invalid date: '+name] += 1
        base={k:scalar(record[k]) for k in KEEP}
        for name in ['SE2 Act','SE3 Act','SE4 Act','QGC0 Act']:base[name]=dates[name]
        base['AQ Section']=record['A Dept'];base['K Section']=record['K Dept']
        for name in PLAN+['QGC4 Act']:
            if dates[name] is not None: milestones.append({**base,'milestone plan':name,'planned date':dates[name]})
        # Power Query unpivots other unexpected columns too. Preserve them for inspection.
        for name,i in extras:
            value=values[i] if i<len(values) else None
            if value not in (None,''): milestones.append({**base,'milestone plan':name,'planned date':scalar(value)})
    ids=Counter(x['PRJ MCR-ID'] for x in projects if x['PRJ MCR-ID'] not in (None,''))
    return {'source':{'filename':Path(filename).name,'format':suffix,'sheet':'Sheet1' if suffix=='.xlsx' else None,'data_note':'读取文件保存的值；不刷新外部链接或重新计算公式。','extra_columns':[x[0] for x in extras]},'summary':{'project_rows':len(projects),'distinct_project_ids':len(ids),'duplicate_id_groups':sum(n>1 for n in ids.values()),'milestone_rows':len(milestones),'component_counts':{k:sum(str(p[col] or '').casefold()=='y' for p in projects) for k,col in COMPONENTS.items()}},'issues':dict(issues),'projects':projects,'milestones':milestones}
