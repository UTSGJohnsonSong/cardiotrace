"""Create an editable Tableau workbook from CardioTrace's committed aggregates.
No participant-level data or statistical refitting. Run with tableauhyperapi+lxml.
"""
import argparse, csv, json, math, hashlib, subprocess, zipfile
from pathlib import Path
from copy import deepcopy
from lxml import etree as E
from tableauhyperapi import HyperProcess, Telemetry, Connection, CreateMode, TableDefinition, TableName, SqlType, Inserter

HERE=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(); ap.add_argument('--repo',type=Path,default=HERE); ap.add_argument('--out',type=Path,default=HERE/'build'/'tableau'); args=ap.parse_args()
REPO=args.repo.resolve(); OUT=args.out.resolve(); OUT.mkdir(parents=True,exist_ok=True)
BLUE='#2a78d6'; ORANGE='#eb6834'; INK='#182c3b'; MUTED='#596871'; PAPER='#f7f6f2'; WHITE='#fcfcfb'; GRID='#e1e0d9'
COLORS={'Age-standardised':BLUE,'Crude':ORANGE,'10-year':BLUE,'5-year':ORANGE,'CardioTrace':BLUE,'Published PCE':ORANGE,'Mortality adaptation':'#72a4ba','Same-input Cox':'#556777','Cox + UACR':BLUE,'GBM / 11 inputs':'#eb6834','GBM + UACR':'#ad7348','Age + sex':'#849398','Reference':'#aab4b8','Higher SBP':ORANGE,'Other':BLUE}
sources={}; plots={}; audit=[]
def read_csv(rel):
    p=REPO/rel; sources[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
    return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def read_json(rel):
    p=REPO/rel; sources[rel]=hashlib.sha256(p.read_bytes()).hexdigest(); return json.loads(p.read_text(encoding='utf-8'))
def num(v): return float(v) if v not in ['',None] else None
def cycle(v): return 'Aug 2021–Aug 2023' if v=='2021-2022' else v.replace('-','–')
def shortcycle(v): return '2021–23*' if v=='2021-2022' else v[:4]+'–'+v[-2:]
def record(x=0,y=0,category='',series='Other',detail='',label='',**kw):
    return dict(X=x,Y=y,Category=category,Series=series,Detail=detail,Label=label,**kw)
def put(name,rows,kind,xtitle='',ytitle='',xrange=None,yrange=None):
    if kind=='interval':
        for r in rows:
            COLORS[r['Category']]=COLORS.get(r['Series'],BLUE)
            r['Series']=r['Category']
    plots[name]=dict(rows=rows,kind=kind,xtitle=xtitle,ytitle=ytitle,xrange=xrange,yrange=yrange)
def interval(category,estimate,low,high,series,detail):
    assert low <= estimate <= high
    # Vertices of a confidence interval, not additional observations.
    return [record(v,category=category,series=series,detail=detail,label='●' if i==1 else '',Vertex=str(i)) for i,v in enumerate([low,estimate,high])]

desc=read_json('reports/descriptive_results.json'); model=read_json('reports/model_results.json'); pce=read_json('reports/pce_results.json'); cohort=read_json('reports/cohort_results.json'); p4=read_json('reports/part4_learning_results.json')
prev=read_csv('data/tableau/cardiotrace_prevalence.csv')
assert len(prev)==187
trend=[]; race=[]; age=[]; cond=[]
for r in prev:
    common=f"{cycle(r['cycle'])} | {r['level']}\nUnweighted n={int(r['n']):,}; PSUs={r['n_psu']}; design df={r['design_dof']}\nInterview weights WTINT2YR. Source: prevalence aggregate."
    if r['dimension']=='Overall':
        for col,ser in [('pct_standardised','Age-standardised'),('pct_crude','Crude')]:
            v=num(r[col]); ci=f"\nDesign-based 95% t CI: {float(r['ci_lo_pct']):.2f}–{float(r['ci_hi_pct']):.2f}%" if ser=='Age-standardised' else '\nNo crude-rate interval exported.'
            trend.append(record(2022.0 if r['cycle']=='2021-2022' else num(r['year']),v,series=ser,detail=f'{ser}: {v:.4f}%'+ci+'\n'+common))
    if r['dimension']=='Race and ethnicity' and r['cycle']=='2021-2022':
        v,lo,hi=map(num,[r['pct_standardised'],r['ci_lo_pct'],r['ci_hi_pct']]); label=f"{r['level']}   {v:.1f}%"
        race+=interval(label,v,lo,hi,'Other',f'{label}\n95% t CI {lo:.2f}–{hi:.2f}%\n'+common)
    if r['dimension']=='Age band':
        assert not r['ci_lo_pct'] and not r['ci_hi_pct']
        age.append(record(y=num(r['pct_crude']),category=r['level'],series=shortcycle(r['cycle']),detail=f"Prevalence {float(r['pct_crude']):.2f}%\nAge-specific; no interval estimated.\n"+common,label=f"{float(r['pct_crude']):.1f}"))
    if r['dimension']=='Condition':
        cond.append(record(2022.0 if r['cycle']=='2021-2022' else num(r['year']),num(r['pct_standardised']),category=r['level'],series=r['level'],detail=f"Age-standardised {float(r['pct_standardised']):.2f}%\n95% t CI {r['ci_lo_pct']}–{r['ci_hi_pct']}%\n"+common))
put('Population trend',trend,'line','Survey period (reference year)','CVD prevalence (%)',(1999,2023),(5,12))
put('Latest race intervals',race,'interval','Age-standardised prevalence (%)','',(0,15))
put('Age profile',age,'heatmap','Survey cycle','Age (years)')
put('Condition trends',cond,'line','Survey period (reference year)','Age-standardised prevalence (%)',(1999,2023),(0,12))

cif=read_csv('reports/tables/cif_by_sbp.csv'); rows=[]
for i,r in enumerate(cif):
    v=float(r['cif_15y_pct']); rows.append(record(v,category=f"{r['stratum_mmhg']} mmHg",series='Higher SBP' if i==4 else 'Other',label=f'{v:.2f}%',detail=f"15-year CVD cumulative incidence: {v:.2f}%\nn={int(r['n']):,}; CVD deaths={r['cvd_deaths']}\nAalen–Johansen; non-CVD death is competing.\nUnadjusted strata, exam weights; not causal.\nSource: cif_by_sbp.csv"))
put('Blood pressure gradient',rows,'bar','15-year CVD mortality (%)','Baseline systolic BP',(0,13))
hr=read_csv('reports/tables/crosscheck_part3.csv'); rows=[]
terms={'systolic_bp':('SBP +10 mmHg',10),'age':('Age +10 years',10),'bmi':('BMI +5 kg/m²',5),'male':('Male vs female',1),'smoke_current':('Current smoker',1),'smoke_former':('Former smoker',1),'pir':('Income ratio +1',1)}
for r in sorted(hr,key=lambda r:list(terms).index(r['term']) if r['term'] in terms else 99):
    if r['term'] not in terms: continue
    label,scale=terms[r['term']]; v,lo,hi=[math.exp(float(r[c])*scale) for c in ['svycoxph_coef','svycoxph_lo95','svycoxph_hi95']]
    rows+=interval(f'{label}   {v:.2f}',v,lo,hi,'Higher SBP' if r['term']=='systolic_bp' else 'Other',f'{label}\nHR {v:.4f}; 95% t CI {lo:.4f}–{hi:.4f}\nR survey::svycoxph; df={r["svycoxph_design_df"]}; n={r["n"]}\nExam weights; adjusted association, not a treatment effect.\nSource: crosscheck_part3.csv; exp(log coefficient × scale).')
put('Adjusted associations',rows,'interval','Adjusted hazard ratio (linear scale)','',(0.5,3.5))
for horizon in [10,5]:
    cal=read_csv(f'reports/tables/calibration_{horizon}y.csv'); rows=[]
    for r in cal:
        rows.append(record(float(r['predicted_pct']),float(r['observed_pct']),category='Decile '+str(int(r['bin'])+1),series=f'{horizon}-year',label='',detail=f"{horizon}-year calibration, decile {int(r['bin'])+1}\nPredicted {r['predicted_pct']}%; observed {r['observed_pct']}%\nn={r['n']}\nOriginal prediction sample; distinct from PCE paired sample.\nSource: calibration_{horizon}y.csv"))
    ceiling=11 if horizon==10 else 4
    rows+=[record(v,v,series='Reference',detail='Perfect calibration: observed = predicted. Visual identity guide, not an observation.') for v in [0,ceiling]]
    put(f'Calibration {horizon}y',rows,'line','Predicted mortality (%)','Observed (%)',(0,ceiling),(0,ceiling))

armnames={'1a_published_ascvd':'Published PCE','1b_mortality_recalibration':'Mortality adaptation','2_same_inputs_refit':'Same-input Cox','3_cardiotrace_refit':'CardioTrace'}
rank=[]; delta=[]
for horizon,test in pce['primary']['tests'].items():
    for arm,r in test['metrics'].items():
        name=armnames[arm]; row=f'{horizon[:-1]}y  ·  {name}'
        rank.append(record(r['c'],category=row,series=name,label=f"{r['c']:.3f}",detail=f"{row}\nSurvey-weighted C = {r['c']:.6f}\nPaired test n={r['n']:,}; evaluable={r['n_evaluable']:,}\nCVD deaths at horizon={r['events_at_horizon']}\nOriginal 10-year PCE score is a historical ranking benchmark.\nHard ASCVD and CVD death are different endpoints.\nSource: pce_results.json"))
    for arm,r in test['delta_c_vs_published_pce'].items():
        name=armnames[arm]; row=f'{horizon[:-1]}y  ·  {name}'
        delta+=interval(f"{row}\n{r['delta']:+.4f}",r['delta'],r['lo'],r['hi'],name,f"{row} minus published PCE\nΔC {r['delta']:+.4f}; 95% CI [{r['lo']:+.4f}, {r['hi']:+.4f}]\n{r['n_boot']} paired PSU bootstrap replicates within strata; conditional on training fits.\nInterval includes zero. Source: pce_results.json")
put('Paired discrimination',rank,'dot','Survey-weighted Harrell C','',(0.75,0.88))
put('Paired differences',delta,'interval','ΔC versus published PCE','',(-0.04,0.05))
p4names={'cox_wide':'Cox + UACR','gbm_p':'GBM / 11 inputs','gbm_wide':'GBM + UACR','floor_age_sex':'Age + sex'}; rows=[]
for r in read_csv('reports/tables/part4_arms.csv'):
    if r['arm']=='cox_p': continue
    label=p4names[r['arm']]; v,lo,hi=map(float,[r['delta_c'],r['delta_lo'],r['delta_hi']])
    rows+=interval(f'{label}  {v:+.4f}',v,lo,hi,label,f"{label} minus 11-input Cox\nΔC {v:+.4f}; 95% CI [{lo:+.4f}, {hi:+.4f}]\nSeparate Part 4 common test sample n=4,641; 191 CVD deaths.\nExploratory feature and model comparison. Source: part4_arms.csv")
put('Part 4 learning',rows,'interval','ΔC versus 11-input Cox','',(-0.09,0.04))
dca=read_csv('reports/tables/decision_curve_primary.csv'); rows=[]
for r in dca:
    if r['horizon_years']!='10': continue
    if r['arm']=='treat_all': continue # omitted visibly in caption to retain a readable scale
    name=armnames.get(r['arm'],'Treat none')
    COLORS['Treat none']='#9ba7ac'
    rows.append(record(float(r['threshold'])*100,float(r['net_benefit'])*100,series=name,detail=f"10-year exploratory decision curve\n{name}; threshold {float(r['threshold'])*100:.1f}%\nNet benefit {float(r['net_benefit'])*100:.4f} per 100\n{r['estimator']}; early censored={r['early_censored']}\nMortality arms only; no confidence intervals or clinical utility claim.\nSource: decision_curve_primary.csv"))
put('Decision curves 10y',rows,'line','CVD-mortality risk threshold (%)','Net benefit per 100',(0,10),(-0.1,2.2))

for name,p in plots.items():
    for coordinate,limits in [('X',p['xrange']),('Y',p['yrange'])]:
        if limits:
            assert all(limits[0]-1e-8 <= r[coordinate] <= limits[1]+1e-8 for r in p['rows']), (name,coordinate,'axis clips data')
    if p['kind']=='interval':
        groups={r['Series'] for r in p['rows']}
        assert len(groups)*3==len(p['rows'])
        assert all(len({r['Category'] for r in p['rows'] if r['Series']==g})==1 for g in groups)
assert len(age)==66 and len(trend)==22 and len(race)==12
assert abs(trend[-2]['Y']-desc['part1']['std_last']*100)<0.0001
assert sum(int(r['n']) for r in cif)==19831

def sub(parent,tag,**a): return E.SubElement(parent,tag,{k:str(v) for k,v in a.items()})
def fmt(parent,attr,value,**more): return sub(parent,'format',attr=attr,value=value,**more)
def rule(parent,element,**attrs):
    node=sub(parent,'style-rule',element=element)
    for k,v in attrs.items(): fmt(node,k.replace('_','-'),v)
    return node

data=OUT/'CardioTrace.hyper'
schema={'X':('real',SqlType.double()),'Y':('real',SqlType.double()),'Sort':('real',SqlType.double()),'Shade':('string',SqlType.text()),'Category':('string',SqlType.text()),'Series':('string',SqlType.text()),'Detail':('string',SqlType.text()),'Label':('string',SqlType.text()),'Vertex':('string',SqlType.text())}
with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
    with Connection(hp.endpoint,str(data),CreateMode.CREATE_AND_REPLACE) as con:
        con.catalog.create_schema('Extract')
        for i,(name,p) in enumerate(plots.items()):
            categories=list(dict.fromkeys(r['Category'] for r in p['rows']))
            for row in p['rows']: row['Sort']=float(categories.index(row['Category']))
            for row in p['rows']: row['Shade']=str(row['Y'])
            p['table']='Chart'+str(i+1); table=TableDefinition(TableName('Extract',p['table']),[TableDefinition.Column(k,t[1]) for k,t in schema.items()]); con.catalog.create_table(table)
            with Inserter(con,table) as ins:
                ins.add_rows([[r.get(k,'' if t[0]=='string' else None) for k,t in schema.items()] for r in p['rows']]); ins.execute()
            actual=con.execute_scalar_query(f'SELECT COUNT(*) FROM "Extract"."{p["table"]}"'); assert actual==len(p['rows'])
            audit.append(dict(sheet=name,rows=actual,kind=p['kind']))

root=E.Element('workbook',{'source-build':'2026.2.2','source-platform':'win','version':'18.1'})
prefs=sub(root,'preferences'); sub(prefs,'preference',name='ui.encoding.shelf.height',value='24')
dss=sub(root,'datasources'); sheets=sub(root,'worksheets')
for name,p in plots.items():
    dsname='hyper.'+p['table']; ds=sub(dss,'datasource',caption=name,inline='true',name=dsname,version='18.1')
    con=sub(ds,'connection',**{'class':'hyper','dbname':'CardioTrace.hyper','schema':'Extract','access_mode':'readonly'})
    sub(con,'relation',name=p['table'],table=f'[Extract].[{p["table"]}]',type='table')
    columns={}
    for k,(typ,_) in schema.items():
        role='dimension' if typ=='string' or k=='X' else 'measure'
        col=sub(ds,'column',datatype=typ,name=f'[{k}]',role=role,type='nominal' if typ=='string' else 'quantitative')
        if k=='Category': col.set('caption',' ')
        if k in ['X','Y']: col.set('default-format','n0.00')
        columns[k]=col
    for k in ['Series','Shade']: sub(ds,'column-instance',column=f'[{k}]',derivation='None',name=f'[none:{k}:nk]',pivot='key',type='nominal')
    dsmark=rule(sub(ds,'style'),'mark')
    dc=sub(dsmark,'encoding',attr='color',field='[none:Series:nk]',type='palette')
    for j,g in enumerate(dict.fromkeys(r['Series'] for r in p['rows'])):
        palette=[BLUE,ORANGE,'#72a4ba','#556777','#ad7348','#a4bbc5']
        m=sub(dc,'map',to=COLORS.get(g,palette[j%len(palette)])); sub(m,'bucket').text='"'+g+'"'
    if p['kind']=='heatmap':
        dc=sub(dsmark,'encoding',attr='color',field='[none:Shade:nk]',type='palette')
        for v in sorted(set(r['Y'] for r in p['rows'])):
            ratio=min(v/40,1); start=[242,247,253]; end=[134,182,239]
            rgb=[round(a+(b-a)*ratio) for a,b in zip(start,end)]; colour='#'+''.join(f'{c:02x}' for c in rgb)
            m=sub(dc,'map',to=colour); sub(m,'bucket').text='"'+str(v)+'"'
    if name in ['Population trend','Condition trends']: columns['X'].set('default-format','n0')
    ws=sub(sheets,'worksheet',name=name)
    layout=sub(ws,'layout-options'); title=sub(layout,'title'); ft=sub(title,'formatted-text'); sub(ft,'run',fontname='Arial',fontsize='13',bold='true',fontcolor=INK).text=name
    table=sub(ws,'table'); view=sub(table,'view'); sub(sub(view,'datasources'),'datasource',name=dsname,caption=name)
    deps=sub(view,'datasource-dependencies',datasource=dsname)
    for col in columns.values(): deps.append(deepcopy(col))
    def f(k,drv=None):
        drv=drv or ('avg' if k in ['Y','Sort'] else ('attr' if k=='Detail' else 'none')); typ='nk' if schema[k][0]=='string' else 'qk'
        return f'[{dsname}].[{drv}:{k}:{typ}]'
    for k in schema:
        drv='Avg' if k in ['Y','Sort'] else ('Attribute' if k=='Detail' else 'None'); typ='nominal' if schema[k][0]=='string' else 'quantitative'
        token='attr' if k=='Detail' else drv.lower()
        sub(deps,'column-instance',column=f'[{k}]',derivation=drv,name=f'[{token}:{k}:{"nk" if typ=="nominal" else "qk"}]',pivot='key',type=typ)
    if p['kind'] in ['bar','dot','interval','heatmap']: sub(view,'sort',**{'class':'computed','column':f('Category'),'direction':'ASC','using':f('Sort')})
    sub(view,'aggregation',value='true')
    sty=sub(table,'style')
    rule(sty,'table',font_family='Arial',font_size='10',color=INK,background_color=WHITE)
    rule(sty,'cell',font_family='Arial',font_size='10',color=MUTED,background_color=WHITE)
    rule(sty,'pane',background_color=WHITE)
    rule(sty,'gridline',line_visibility='off')
    rule(sty,'zeroline',line_visibility='on',stroke_size='1',color=GRID)
    ar=rule(sty,'axis',font_family='Arial',font_size='10',color=MUTED)
    for axis,title,ran in [('X',p['xtitle'],p['xrange']),('Y',p['ytitle'],p['yrange'])]:
        fmt(ar,'title',title,field=f(axis))
        if ran:
            enc=sub(ar,'encoding',attr='space',field=f(axis),type='space',**{'class':'0','min':ran[0],'max':ran[1],'range-type':'fixed','field-type':'quantitative','scope':'cols' if axis=='X' else 'rows'})
    # Categorical color mappings are fixed across the report.
    legend=rule(sty,'mark')
    if p['kind']!='heatmap':
        encoding=sub(legend,'encoding',attr='color',field=f('Series'),type='palette')
        groups=list(dict.fromkeys(r['Series'] for r in p['rows']))
        palette=[BLUE,ORANGE,'#72a4ba','#556777','#ad7348','#a4bbc5']
        for j,g in enumerate(groups):
            m=sub(encoding,'map',to=COLORS.get(g,palette[j%len(palette)])); sub(m,'bucket').text='"'+g+'"'
    pane=sub(sub(table,'panes'),'pane',**{'selection-relaxation-option':'selection-relaxation-allow'})
    sub(sub(pane,'view'),'breakdown',value='auto')
    kind=p['kind']; mark={'line':'Line','interval':'Line','heatmap':'Square','bar':'Bar','dot':'Circle','scatter':'Circle'}[kind]
    sub(pane,'mark',**{'class':mark})
    if kind=='heatmap': sub(pane,'mark-sizing',**{'mark-sizing-setting':'marks-scaling-off'})
    enc=sub(pane,'encodings')
    sub(enc,'color',column=f('Shade') if kind=='heatmap' else f('Series'))
    sub(enc,'tooltip',column=f('Detail'))
    if kind in ['heatmap','bar','dot']: sub(enc,'text',column=f('Label'))
    if kind in ['scatter','interval']: sub(enc,'lod',column=f('Category'))
    tips=sub(pane,'customized-tooltip'); ft=sub(tips,'formatted-text'); sub(ft,'run',fontname='Arial',fontsize='11').text='<'+f('Detail')+'>'
    ps=sub(pane,'style'); mr=rule(ps,'mark',mark_labels_show='true' if kind in ['heatmap','bar','dot'] else 'false',mark_labels_cull='false')
    if kind=='heatmap': fmt(mr,'size','2.022099494934082')
    sub(table,'rows').text=f('Category') if kind in ['bar','dot','interval','heatmap'] else f('Y')
    sub(table,'cols').text=f('Series') if kind=='heatmap' else f('X')

W,H=1380,940
dashboards=sub(root,'dashboards'); dashboard_sheets={}; zid=0
def dashboard(name):
    global zid
    d=sub(dashboards,'dashboard',name=name); rule(sub(d,'style'),'dashboard',background_color=PAPER)
    sub(d,'size',maxheight=H,maxwidth=W,minheight=H,minwidth=W)
    zones=sub(d,'zones'); dashboard_sheets[name]=[]; return name,zones
def zone(d,x,y,w,h,kind=None,name=None,bg=None):
    global zid; zid+=1
    a=dict(x=round(x/W*100000),y=round(y/H*100000),w=round(w/W*100000),h=round(h/H*100000),id=zid)
    if kind:a['type-v2']=kind
    if name:a['name']=name
    z=sub(d[1],'zone',**a)
    return z
def zs(z,bg=None,margin=0):
    st=sub(z,'zone-style')
    for k,v in [('border-style','none'),('border-width','0'),('margin',margin),('padding','0')]: fmt(st,k,v)
    if bg:fmt(st,'background-color',bg)
def text(d,x,y,w,h,content,size=12,color=INK,font='Arial',bold=False,bg=None):
    z=zone(d,x,y,w,h,'text'); ft=sub(z,'formatted-text'); sub(ft,'run',fontname=font,fontsize=size,fontcolor=color,bold=str(bold).lower()).text=content; zs(z,bg); return z
def chart(d,name,x,y,w,h):
    z=zone(d,x,y,w,h,name=name); z.set('show-title','false'); zs(z,WHITE,8); dashboard_sheets[d[0]].append(name)
def heading(d,n,title,subtitle):
    text(d,32,20,990,24,'CARDIOTRACE  /  NHANES RESEARCH ATLAS',11,BLUE,bold=True)
    text(d,1100,20,245,24,n+'   /   03',11,MUTED)
    text(d,32,53,1316,52,title,30,INK,'Georgia')
    text(d,34,107,1308,32,subtitle,12,MUTED)
def kpi(d,x,value,label,note,color=BLUE):
    text(d,x,146,310,106,'',bg=WHITE)
    text(d,x+14,155,288,44,value,28,color,'Georgia')
    text(d,x+14,200,288,24,label,11,INK,bold=True)
    text(d,x+14,226,288,22,note,10,MUTED)
def caption(d,x,y,w,title,note):
    text(d,x,y,w,26,title,14,INK,bold=True); text(d,x,y+28,w,37,note,10,MUTED)
def footer(d,content):
    text(d,34,874,1310,52,content+'\nSOURCE  CardioTrace / main 9517c6f · CDC NHANES · Published aggregates only · Hover marks for estimates and provenance.',10,MUTED)

d=dashboard('01  Population burden')
heading(d,'01','Aging changes the picture','Part 1 + 2  ·  US adults 20+  ·  Repeated cross-sectional surveys, 1999–2018 and Aug 2021–Aug 2023')
kpi(d,32,f"{desc['part1']['n_adults']:,}",'adults across 11 survey cycles','Interview-weighted population estimates')
kpi(d,366,f"{desc['part1']['crude_last']*100:.2f}%",'latest crude CVD prevalence','8.02% in 1999–2000',ORANGE)
kpi(d,700,f"{desc['part1']['std_last']*100:.2f}%",'latest age-standardised prevalence','8.69% in 1999–2000')
kpi(d,1034,f"{desc['part2']['gap']*100:+.2f} pp",'latest cycle vs pre-period trend','95% CI −0.76 to +1.66 pp',MUTED)
caption(d,34,297,730,'01 / Crude burden rises; the standardised trend is uncertain','BLUE  Age-standardised    ORANGE  Crude  ·  Rates in percent; hover the blue line for design-based CIs.')
chart(d,'Population trend',26,360,792,259)
caption(d,850,297,495,'02 / Latest race–ethnicity estimates','Values are point estimates; lines show 95% t CIs. NH = non-Hispanic.')
chart(d,'Latest race intervals',838,360,518,259)
caption(d,34,643,890,'03 / The age gradient, cycle by cycle','Age-specific prevalence (%)  ·  No intervals were estimated for these cells. Darker cells indicate higher prevalence.')
chart(d,'Age profile',26,703,911,155)
text(d,958,656,388,198,'READ THE CHANGE CAREFULLY\n\nThe pre-pandemic standardised slope is −0.59 pp per decade (95% CI −1.22 to +0.04).\n\nOne redesigned post-pandemic cycle cannot identify a pandemic effect.',12,INK,bg=WHITE)
footer(d,'Self-reported CVD; age-standardisation uses the 2000 US population. *2021–23 = Aug 2021–Aug 2023, a redesigned survey period.')

d=dashboard('02  Mortality risk')
heading(d,'02','Higher blood pressure, higher observed risk','Part 3  ·  Baseline 1999–2014, ages 40–79, free of diagnosed CVD  ·  Mortality follow-up through 2019')
kpi(d,32,'20,736','participants in the mortality cohort','925 CVD deaths over full follow-up')
kpi(d,366,'2,711','deaths from competing causes','Competing events retained in incidence')
kpi(d,700,'1.12','adjusted HR per +10 mmHg SBP','R survey model; 95% CI 1.08–1.17',ORANGE)
kpi(d,1034,'17,890','participants in adjusted Cox analysis','Complete fitted covariates; exam weights')
caption(d,34,298,582,'01 / Absolute risk increases across BP strata','15-year Aalen–Johansen CVD mortality  ·  n=19,831 with BP; unadjusted, no intervals exported.')
chart(d,'Blood pressure gradient',26,360,625,258)
caption(d,692,298,650,'02 / Adjusted associations, independently checked in R','Seven selected terms; 95% t CIs, df 123. Smoking reference: never. Values = HR; null HR = 1.')
chart(d,'Adjusted associations',675,360,681,258)
caption(d,34,642,620,'03 / 10-year calibration','Blue = decile calibration curve; grey = perfect calibration. Original sample; PCE sample differs.')
chart(d,'Calibration 10y',26,704,625,151)
caption(d,694,642,640,'04 / 5-year calibration','Orange = decile calibration curve; grey = perfect calibration. Hover for decile sizes and estimates.')
chart(d,'Calibration 5y',675,704,681,151)
footer(d,'BP and model associations are observational, not treatment effects. Tobin medication correction follows the protocol; inference uses MEC weights.')

d=dashboard('03  Model evidence')
heading(d,'03','No demonstrated superiority over historical PCE','Part 3 benchmark + Part 4 learning  ·  Paired comparisons within each test sample  ·  PCE is a prespecified historical benchmark')
kpi(d,32,'3,302','paired 10-year test participants','2005–2008 baseline; primary ethnicity set')
kpi(d,366,'4,985','paired 5-year test participants','2009–2014 baseline; primary ethnicity set')
kpi(d,700,'−0.011','10-year ΔC: CardioTrace minus PCE','95% CI −0.021 to +0.0004',MUTED)
kpi(d,1034,'+0.014','5-year ΔC: CardioTrace minus PCE','95% CI −0.011 to +0.040',MUTED)
caption(d,34,298,585,'01 / Four arms, the same participants within each horizon','Survey-weighted Harrell C  ·  ORANGE published PCE; BLUE CardioTrace. Higher means better ranking.')
chart(d,'Paired discrimination',26,360,625,258)
caption(d,694,298,646,'02 / Every paired difference interval includes zero','ΔC versus published PCE  ·  95% paired PSU bootstrap CIs; 200 replicates, conditional on training fits.')
chart(d,'Paired differences',675,360,681,258)
caption(d,34,642,620,'03 / Adding UACR helped in a separate learning experiment','Part 4: n=4,641; 191 CVD deaths  ·  ΔC versus 11-input Cox. This sample differs from PCE.')
chart(d,'Part 4 learning',26,704,625,151)
caption(d,694,642,646,'04 / Exploratory 10-year decision curves','Blue: CardioTrace; light blue: adaptation; grey: same-input Cox. Treat-none = 0; treat-all omitted. No CIs.')
chart(d,'Decision curves 10y',675,704,681,151)
footer(d,'Endpoint mismatch: PCE predicts hard ASCVD; this study observes CVD death. At 5 years, original 10-year PCE scores are used only for ranking.')

windows=sub(root,'windows',**{'source-height':'30'})
for name in plots:
    win=sub(windows,'window',**{'class':'worksheet','name':name}); cards=sub(win,'cards')
    edge=sub(cards,'edge',name='left'); strip=sub(edge,'strip',size='160')
    for typ in ['pages','filters','marks']: sub(strip,'card',type=typ)
    edge=sub(cards,'edge',name='top')
    for typ in ['columns','rows','title']: sub(sub(edge,'strip',size='31'),'card',type=typ)
    sub(sub(win,'viewpoint'),'zoom',type='entire-view')
for name,names in dashboard_sheets.items():
    win=sub(windows,'window',**{'class':'dashboard','name':name,'maximized':'true'}); vps=sub(win,'viewpoints')
    for sn in names: sub(sub(vps,'viewpoint',name=sn),'zoom',type='entire-view')
    sub(win,'active',id='-1')
# Balance chart heights after the dashboard's narrative blocks are assembled.
for z in root.findall('dashboards/dashboard/zones/zone'):
    y=float(z.get('y'))*H/100000
    if 290<=y<350: z.set('y',str(round((y-26)/H*100000)))
    elif 359<=y<=361: z.set('y',str(round(335/H*100000))); z.set('h',str(round(265/H*100000)))
    elif 641<=y<=681: z.set('y',str(round((y-24)/H*100000)))
    elif 702<=y<=705: z.set('y',str(round(680/H*100000))); z.set('h',str(round(180/H*100000)))
twb=OUT/'CardioTrace Research Atlas.twb'; twb.write_bytes(E.tostring(root,pretty_print=True,encoding='utf-8',xml_declaration=True))
with zipfile.ZipFile(OUT/'CardioTrace Research Atlas.twbx','w',zipfile.ZIP_DEFLATED) as z:
    z.write(twb,twb.name); z.write(data,data.name)
commit='9517c6fbcd8a8e4f42ac9356e27f539689d64322'
for rel,digest in sources.items():
    published=subprocess.check_output(['git','-C',str(REPO),'show',f'{commit}:{rel}'])
    assert published==(REPO/rel).read_bytes().replace(b'\r\n',b'\n'), f'{rel} changed: review the atlas labels and source version before rebuilding.'
(OUT/'data-audit.json').write_text(json.dumps(dict(source_commit=commit,source_sha256=sources,source_sha256_lf={rel:hashlib.sha256((REPO/rel).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for rel in sources},charts=audit,participants_in_extract=False,analysis_refitted=False,validation={'all_plotted_values_within_axes':True,'every_interval_is_a_separate_series':True,'prevalence_187_source_cells':True,'age_heatmap_66_cells':True,'bp_strata_total_n':19831},notes=['X/Y are chart coordinates; CI vertices are not separate observations.','Latest Aug 2021–Aug 2023 period is displayed at reference year 2022, replacing the internal CSV time coordinate for presentation only.','Prevalence values use percentage points; no fabricated age-specific CI.','Hazard ratios are exp of R coefficients and interval limits after stated unit scaling.','Four calibration identity-guide vertices are visual guides, not observations.','Heatmap colour interpolates between light blue shades over 0–40%; estimates are printed unchanged.','Native charts preserve hover details; underlying aggregate rows are editable.']),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(workbook=str(twb),sheets=len(plots),dashboards=len(dashboard_sheets),rows=sum(len(p['rows']) for p in plots.values())),ensure_ascii=False))
