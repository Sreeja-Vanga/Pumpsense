"""Seeded synthetic generator. Same code for starter (--points 5000 --fac 1 --pumps 4 --tanks 8 --valves 8) and full scale."""
import argparse,json,hashlib,os,math
import numpy as np,pandas as pd
from physics import pump_state,mode_speed,MODES,simulate,ASSUMPTIONS
ap=argparse.ArgumentParser()
for k,v in dict(seed=20261022,fac=3,pumps=20,tanks=30,valves=60,points=100000).items(): ap.add_argument('--'+k,type=int,default=v)
ap.add_argument('--out',default='data'); a=ap.parse_args()
rng=np.random.default_rng(a.seed); os.makedirs(a.out,exist_ok=True); P=a.pumps
assert 2*P<=a.valves<=3*P
ID=lambda p,n,w=3:f"{p}-{n:0{w}d}"
t0=pd.Timestamp('2026-09-01'); dstr=lambda d:str((t0-pd.Timedelta(days=d)).date())
tk,pk=np.array_split(np.arange(a.tanks),a.fac),np.array_split(np.arange(P),a.fac)
NM=['Hyderabad Water Works','Vizag Process Utilities','Pune Cooling Plant']; ST=['WATER_TREATMENT','PROCESS_UTILITY','DISTRICT_COOLING']
fac=[dict(facility_id=ID('FAC',i+1),name=NM[i%3]+('' if i<3 else f' {i}'),site_type=ST[i%3],timezone='Asia/Kolkata',status='ACTIVE',commissioned_on=dstr(int(rng.integers(900,4000)))) for i in range(a.fac)]
tanks,pumps,valves,pipes,pv=[],[],[],[],[]; extra=a.valves-2*P
# ---- Topology: src tank -> [isolation] -> suction valve -> pump -> discharge valve -> dest tank
for f in range(a.fac):
  fid=ID('FAC',f+1); nt,npf=len(tk[f]),len(pk[f]); nd=min(npf,nt-1); ns=nt-nd
  for t in tk[f]: tanks.append(dict(tank_id=ID('TANK',t+1),facility_id=fid,capacity_m3=int(rng.choice([250,400,600,800,1200,1600,2000])),min_level_pct=5,max_level_pct=95,fluid='WATER',status='IN_SERVICE'))
  for j,pi in enumerate(pk[f]):
    pid=ID('PUMP',pi+1); src=ID('TANK',tk[f][nd+j%ns]+1); dst=ID('TANK',tk[f][j%nd]+1)
    qn=float(rng.choice([40,60,80,100,120,150])); p0=round(float(rng.uniform(6,10)),2); inst=dstr(int(rng.integers(200,1800)))
    pumps.append(dict(pump_id=pid,facility_id=fid,src_tank_id=src,dest_tank_id=dst,q_nom_m3h=qn,shutoff_head_bar=p0,rated_kw=round(qn*p0*0.04,1),status='RUNNING',installed_on=inst))
    chain=[src]
    for role,typ in ([('ISOLATION','GATE')] if pi<extra else [])+[('SUCTION','GATE'),('DISCHARGE','BALL')]:
      vid=ID('VALVE',len(valves)+1); op=100 if rng.random()<.9 else int(rng.integers(80,96))
      valves.append(dict(valve_id=vid,facility_id=fid,valve_type=typ,role=role,state='OPEN' if op==100 else 'THROTTLED',open_pct=op,installed_on=inst))
      pv.append(dict(pump_id=pid,valve_id=vid,role=role,effective_from=inst,effective_to=None))
      if role=='DISCHARGE': chain.append(pid)
      chain.append(vid)
    chain.append(dst)
    for s,(x,y) in enumerate(zip(chain,chain[1:])): pipes.append(dict(pipe_id=ID('PIPE',len(pipes)+1),facility_id=fid,serves_pump_id=pid,seq=s+1,from_node_id=x,to_node_id=y,diameter_mm=int(rng.choice([100,150,200,250])),length_m=int(rng.integers(15,400)),status='IN_SERVICE'))
vopen={v['valve_id']:v['open_pct']/100 for v in valves}; vfm={p['pump_id']:1.0 for p in pumps}
for r in pv: vfm[r['pump_id']]*=vopen[r['valve_id']]
sens=[]
def S(fid,at,aid,pid,me,un,lo,hi): sens.append(dict(sensor_id=ID('SNS',len(sens)+1),facility_id=fid,asset_type=at,asset_id=aid,pump_id=pid,measurand=me,unit=un,range_min=lo,range_max=hi,status='ACTIVE',installed_on=str(t0.date())))
for p in pumps:
  S(p['facility_id'],'PUMP',p['pump_id'],p['pump_id'],'FLOW','m3/h',0,300); S(p['facility_id'],'PUMP',p['pump_id'],p['pump_id'],'PRESSURE','bar',0,15); S(p['facility_id'],'TANK',p['dest_tank_id'],p['pump_id'],'INLET_FLOW','m3/h',0,300)
for t in tanks: S(t['facility_id'],'TANK',t['tank_id'],None,'LEVEL','%',0,100)
# ---- Time base, operating modes, physics
qn=np.array([p['q_nom_m3h'] for p in pumps]); p0=np.array([p['shutoff_head_bar'] for p in pumps]); vf=np.array([vfm[p['pump_id']] for p in pumps])
ti={t['tank_id']:i for i,t in enumerate(tanks)}; di=np.array([ti[p['dest_tank_id']] for p in pumps]); si=np.array([ti[p['src_tank_id']] for p in pumps]); cap=np.array([t['capacity_m3'] for t in tanks],float)
nS=len(sens); T=math.ceil(a.points/nS); ts=t0+pd.to_timedelta(np.arange(T)*5,unit='min')
base=mode_speed(ts.hour.values); spd=base[:,None]*(1+rng.normal(0,.008,(T,P)))
modes=[]; ch=[0]+[i for i in range(1,T) if base[i]!=base[i-1]]+[T]
for f in fac:
  for k in range(len(ch)-1): modes.append(dict(mode_id=ID('MODE',len(modes)+1,4),facility_id=f['facility_id'],mode_name=MODES[float(base[ch[k]])],speed_factor=float(base[ch[k]]),effective_from=ts[ch[k]],effective_to=ts[ch[k+1]] if ch[k+1]<T else None))
# ---- Labelled scenarios (ground truth) injected into the process or into the measurement only
block=np.zeros((T,P)); leak=np.zeros((T,P)); eff=np.ones((T,P)); events,faults,busy=[],[],[[] for _ in range(P)]
for kind,cat,n in [('LEAK','PROCESS',6),('BLOCKAGE','PROCESS',6),('PUMP_DEGRADATION','PROCESS',5),('SENSOR_STUCK','SENSOR',3),('SENSOR_DRIFT','SENSOR',3),('SENSOR_SPIKE','SENSOR',3)]:
  for _ in range(max(1,round(n*P/20))):
    for _t in range(80):
      j=int(rng.integers(P)); d=int(rng.integers(max(12,T//18),max(13,T//6))); s=int(rng.integers(T//8,max(T//8+1,T-d-10)))
      if all(s>=e2+20 or s+d<=s2-20 for s2,e2 in busy[j]): break
    e=min(s+d,T); busy[j].append((s,e)); sid=None
    if kind=='LEAK': sev=float(rng.uniform(.18,.4)); leak[s:e,j]=sev
    elif kind=='BLOCKAGE': sev=float(rng.uniform(.3,.55)); block[s:e,j]=sev
    elif kind=='PUMP_DEGRADATION': sev=float(rng.uniform(.15,.3)); eff[s:e,j]=1-sev*np.linspace(.2,1,e-s)
    else:
      c=3*j+int(rng.choice([0,1,2],p=[.4,.2,.4])); faults.append((kind,c,s,e)); sid=sens[c]['sensor_id']; sev=float(rng.uniform(.15,.4))
    events.append(dict(scenario_id=ID('SCN',len(events)+1),issue_type=kind,category=cat,facility_id=pumps[j]['facility_id'],pump_id=pumps[j]['pump_id'],sensor_id=sid,start_ts=ts[s],end_ts=ts[e-1],severity=round(sev,3),_j=j,_s=s,_e=e))
q,p,qi=pump_state(qn,p0,spd,eff,block,leak,vf)
lev=np.zeros((T,a.tanks)); L=np.full(a.tanks,50.)
for t in range(T):   # tank mass balance with proportional outflow control
  inflow=np.bincount(di,qi[t],a.tanks); draw=np.bincount(si,q[t],a.tanks); dem=np.bincount(di,qn*spd[t]*vf,a.tanks)
  L=np.clip(L+(inflow-dem*(1+.5*(L-50)/50)+draw*(1+.5*(50-L)/50)-draw)*(5/60)/cap*100,0,100); lev[t]=L
M=np.zeros((T,nS)); M[:,0:3*P:3]=q*(1+rng.normal(0,.01,q.shape)); M[:,1:3*P:3]=p*(1+rng.normal(0,.008,p.shape)); M[:,2:3*P:3]=qi*(1+rng.normal(0,.01,q.shape)); M[:,3*P:]=lev+rng.normal(0,.25,lev.shape)
for kind,c,s,e in faults:   # sensor faults corrupt the MEASUREMENT only; the process stays healthy
  if kind=='SENSOR_STUCK': M[s:e,c]=M[s,c]
  elif kind=='SENSOR_DRIFT': M[s:e,c]+=np.linspace(0,.25,e-s)*M[:s,c].mean()
  else: M[np.arange(s,e,4),c]*=1.6
# ---- Alarms derived from measured data by rules (the rule engine cannot tell process from sensor -> PROCESS)
alm=[]
def eps(m):
  r=(np.convolve(m.astype(int),np.ones(3,int))[:len(m)]>=3).astype(int); d=np.diff(np.r_[0,r,0]); return zip(np.where(d==1)[0],np.where(d==-1)[0]-1)
def add(kind,c,at,aid,pj,m,fid):
  for s,e in eps(m): alm.append(dict(facility_id=fid,asset_type=at,asset_id=aid,pump_id=pj,sensor_id=sens[c]['sensor_id'],alarm_type=kind,severity='CRITICAL' if e-s>=12 else 'WARNING',raised_at=ts[s],cleared_at=ts[min(e+1,T-1)],state='CLEARED',alarm_category='PROCESS',_s=s,_e=e))
for j,pp in enumerate(pumps):
  pe=pump_state(qn[j],p0[j],spd[:,j],1,0,0,vf[j])[1]; eq=qn[j]*spd[:,j]*vf[j]; f_=pp['facility_id']; i_=pp['pump_id']
  add('FLOW_IMBALANCE',3*j,'PUMP',i_,i_,np.abs(M[:,3*j]-M[:,3*j+2])/qn[j]>.06,f_); add('PRESSURE_DEVIATION',3*j+1,'PUMP',i_,i_,np.abs(M[:,3*j+1]/pe-1)>.15,f_); add('FLOW_DEVIATION',3*j,'PUMP',i_,i_,np.abs(M[:,3*j]/eq-1)>.2,f_)
t2p={pp['dest_tank_id']:pp['pump_id'] for pp in reversed(pumps)}
for k,t in enumerate(tanks): c=3*P+k; add('TANK_LEVEL_HIGH',c,'TANK',t['tank_id'],t2p.get(t['tank_id']),M[:,c]>90,t['facility_id']); add('TANK_LEVEL_LOW',c,'TANK',t['tank_id'],t2p.get(t['tank_id']),M[:,c]<10,t['facility_id'])
alm.sort(key=lambda r:(r['raised_at'],r['asset_id']))
for i,r in enumerate(alm): r['alarm_id']=ID('ALM',i+1,6)
# ---- Telemetry (flattened from M) + injected edge cases
n=a.points; V=M.ravel()[:n].copy(); ii=np.arange(n); sc=ii%nS; tt=ii//nS
lv=np.where(sc>=3*P)[0]; lv=lv[lv>n//10]; bad=rng.choice(lv,3,replace=False); V[bad]=100+rng.uniform(3,12,3)
U=np.array([s['unit'] for s in sens]); SID=np.array([s['sensor_id'] for s in sens])
tel=pd.DataFrame(dict(telemetry_id=[ID('TEL',i+1,6) for i in range(n)],sensor_id=SID[sc],ts=ts[tt],value=np.round(V,3),unit=U[sc],quality='GOOD'))
edges=[]; E=lambda it,tb,rid,dt:edges.append(dict(case_id=ID('EDGE',len(edges)+1),issue_type=it,table_name=tb,record_id=rid,detail=dt))
for b in bad: E('TANK_LEVEL_EXCEEDS_CAPACITY','telemetry',tel.telemetry_id[b],f'level {tel.value[b]}% > 100%')
for fn,tn in [('TANK-001','VALVE-999'),('PUMP-999','TANK-001')]:
  pid_=ID('PIPE',len(pipes)+1); pipes.append(dict(pipe_id=pid_,facility_id='FAC-001',serves_pump_id=None,seq=None,from_node_id=fn,to_node_id=tn,diameter_mm=150,length_m=50,status='IN_SERVICE')); E('PIPE_REFERENCES_MISSING_NODE','pipe',pid_,f'{fn}->{tn}')
for e in events:
  if e['issue_type']=='LEAK': E('FLOW_CONSERVATION_VIOLATED','gt_events',e['scenario_id'],f"pump {e['pump_id']} leak: outflow - inflow > 6% tolerance")
for r in alm:
  if r['asset_type']=='PUMP' and any(e['category']=='SENSOR' and e['pump_id']==r['pump_id'] and r['_s']<=e['_e'] and r['_e']>=e['_s'] for e in events): E('SENSOR_FAULT_LABELLED_AS_PROCESS','alarm',r['alarm_id'],f"{r['alarm_type']} raised as PROCESS while a sensor fault was active")
# ---- Simulation runs (the last two lack config on purpose: edge case)
sims=[]; cmap={t['tank_id']:t['capacity_m3'] for t in tanks}; SC=['NOMINAL','SPEED_UP','VALVE_THROTTLE','LEAK_WHAT_IF','BLOCKAGE_WHAT_IF','DEGRADATION_WHAT_IF']
u=lambda lo,hi:round(float(rng.uniform(lo,hi)),2)
for i in range(14):
  pp=pumps[int(rng.integers(P))]; k=SC[i%6]; c=dict(speed=1.0,eff=1.0,block=0.0,leak=0.0,valve_open=round(vfm[pp['pump_id']],3),duration_h=6)
  if k=='SPEED_UP': c['speed']=u(1.05,1.25)
  elif k=='VALVE_THROTTLE': c['valve_open']=u(.5,.8)
  elif k=='LEAK_WHAT_IF': c['leak']=u(.1,.35)
  elif k=='BLOCKAGE_WHAT_IF': c['block']=u(.2,.5)
  elif k=='DEGRADATION_WHAT_IF': c['eff']=u(.7,.9)
  out=simulate(c,pp,cmap[pp['dest_tank_id']]); sid=f'SIM-2026-{i+1:06d}'
  sims.append(dict(simulation_id=sid,facility_id=pp['facility_id'],pump_id=pp['pump_id'],scenario_type=k,config_json=None if i>=12 else json.dumps(c),assumptions=ASSUMPTIONS,output_json=json.dumps(out),seed=a.seed,created_at=t0+pd.Timedelta(hours=i),status='COMPLETED',source='GENERATOR'))
  if i>=12: E('SIMULATION_OUTPUT_LACKS_INPUT_CONFIG','simulation_run',sid,'config_json is NULL')
pipe=pd.DataFrame(pipes); pipe['seq']=pipe.seq.astype('Int64')
D=dict(facility=pd.DataFrame(fac),tank=pd.DataFrame(tanks),pump=pd.DataFrame(pumps),valve=pd.DataFrame(valves),pipe=pipe,pump_valve=pd.DataFrame(pv),sensor=pd.DataFrame(sens),telemetry=tel,operating_mode=pd.DataFrame(modes),
 alarm=pd.DataFrame(alm)[['alarm_id','facility_id','asset_type','asset_id','pump_id','sensor_id','alarm_type','severity','raised_at','cleared_at','state','alarm_category']],simulation_run=pd.DataFrame(sims),
 gt_events=pd.DataFrame(events).drop(columns=['_j','_s','_e']),gt_edge_cases=pd.DataFrame(edges))
# ---- Validation
PK=dict(facility='facility_id',tank='tank_id',pump='pump_id',valve='valve_id',pipe='pipe_id',sensor='sensor_id',telemetry='telemetry_id',operating_mode='mode_id',alarm='alarm_id',simulation_run='simulation_id',gt_events='scenario_id')
FK=[('tank','facility_id','facility'),('pump','facility_id','facility'),('pump','src_tank_id','tank'),('pump','dest_tank_id','tank'),('valve','facility_id','facility'),('pipe','facility_id','facility'),('pump_valve','pump_id','pump'),('pump_valve','valve_id','valve'),('sensor','facility_id','facility'),('telemetry','sensor_id','sensor'),('alarm','sensor_id','sensor'),('alarm','facility_id','facility'),('operating_mode','facility_id','facility'),('simulation_run','pump_id','pump')]
nodes=set(D['tank'].tank_id)|set(D['valve'].valve_id)|set(D['pump'].pump_id); ok=D['pipe'][D['pipe'].from_node_id.isin(nodes)&D['pipe'].to_node_id.isin(nodes)]; comp={}
for f in fac:   # pumps are the only links between tanks, so facilities form hydraulic zones; rule = no orphan assets, every zone is a connected line
  fid=f['facility_id']; sub=ok[ok.facility_id==fid]; adj={}
  for x,y in zip(sub.from_node_id,sub.to_node_id): adj.setdefault(x,set()).add(y); adj.setdefault(y,set()).add(x)
  seen,zones=set(),0
  for r0 in adj:
    if r0 in seen: continue
    zones+=1; st=[r0]
    while st:
      x=st.pop()
      if x not in seen: seen.add(x); st.extend(adj[x]-seen)
  mine={n for d_,c_ in((D['tank'],'tank_id'),(D['valve'],'valve_id'),(D['pump'],'pump_id')) for n in d_[d_.facility_id==fid][c_]}
  comp[fid]=dict(hydraulic_zones=zones,orphan_assets=len(mine-set(adj)))
lvl_ids=set(D['sensor'][D['sensor'].measurand=='LEVEL'].sensor_id); resid=np.abs(M[:,0:3*P:3]-M[:,2:3*P:3])/qn>.06; inev=np.zeros((T,P),bool)
for e in events: inev[e['_s']:e['_e'],e['_j']]=True
VAL=dict(pk_unique={t:bool(D[t][k].is_unique) for t,k in PK.items()},fk_orphans={f'{c}.{col}':int((~D[c][col].dropna().isin(D[p_][PK[p_]])).sum()) for c,col,p_ in FK},
 enums_ok=bool(D['valve'].state.isin(['OPEN','THROTTLED','CLOSED']).all() and D['alarm'].severity.isin(['WARNING','CRITICAL']).all()),
 date_order_ok=bool((D['alarm'].cleared_at>=D['alarm'].raised_at).all()),topology_connected_per_facility=comp,
 expected_edge_cases=dict(pipes_missing_node=int((~D['pipe'].index.isin(ok.index)).sum()),level_over_100=int(((tel.value>100)&tel.sensor_id.isin(lvl_ids)).sum()),sim_missing_config=int(D['simulation_run'].config_json.isna().sum()),
  sensor_fault_labelled_process=int((D['gt_edge_cases'].issue_type=='SENSOR_FAULT_LABELLED_AS_PROCESS').sum())),
 flow_conservation=dict(violations=int(resid.sum()),outside_labelled_scenarios=int((resid&~inev).sum()),note='6% tolerance; unlabelled exceedances are measurement noise'),
 telemetry_rows=len(tel),edge_cases_in_ground_truth=len(edges))
json.dump(VAL,open(f'{a.out}/validation_summary.json','w'),indent=1,sort_keys=True,default=str)
# ---- Export CSV + SQL seed + manifest
def sv(v):
  if v is None or v is pd.NA or v is pd.NaT or (isinstance(v,float) and math.isnan(v)): return 'NULL'
  return str(v) if isinstance(v,(int,float,np.number)) else "'"+str(v).replace("'","''")+"'"
man={}
with open(f'{a.out}/seed.sql','w') as sq:
  for t,d in D.items():
    d.to_csv(f'{a.out}/{t}.csv',index=False); man[t]=dict(rows=len(d),sha256=hashlib.sha256(open(f'{a.out}/{t}.csv','rb').read()).hexdigest())
    for i in range(0,len(d),1000): sq.write(f"INSERT INTO {t} ({','.join(d.columns)}) VALUES "+",".join("("+",".join(sv(v) for v in r)+")" for r in d.iloc[i:i+1000].itertuples(index=False))+";\n")
json.dump(dict(generator='generate.py',args=vars(a),source='fully synthetic - no external data, no licences involved',tables=man),open(f'{a.out}/source_manifest.json','w'),indent=1,sort_keys=True)
print(json.dumps({k:v['rows'] for k,v in man.items()}))
