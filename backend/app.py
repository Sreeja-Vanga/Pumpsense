import os,json
import pymysql,pandas as pd
from flask import Flask,jsonify,request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
import ml
from physics import simulate,ASSUMPTIONS
class JP(DefaultJSONProvider):
    default=staticmethod(lambda o:o.item() if hasattr(o,'item') else (o.isoformat(sep=' ') if hasattr(o,'hour') else o.isoformat()) if hasattr(o,'isoformat') else float(o) if hasattr(o,'is_finite') else str(o))
app=Flask(__name__); app.json=JP(app); CORS(app)
def q(sql,a=None):
  c=pymysql.connect(host=os.getenv('DB_HOST','127.0.0.1'),user=os.getenv('DB_USER','root'),password=os.getenv('DB_PASSWORD',''),database=os.getenv('DB_NAME','pumpsense'),cursorclass=pymysql.cursors.DictCursor,autocommit=True)
  try:
    with c.cursor() as cur: cur.execute(sql,a); return cur.fetchall()
  finally: c.close()
df=lambda s,a=None:pd.DataFrame(q(s,a)); S={}
def model():
  if 'm' not in S: S['m']=ml.train(df('select sensor_id,ts,value from telemetry'),df('select * from sensor'),df('select * from pump'),df('select pv.pump_id,v.open_pct from pump_valve pv join valve v using(valve_id)'),df('select * from gt_events'))
  return S['m']
fmt=lambda t:pd.Timestamp(t).strftime('%m-%d %H:%M')
PLAY=dict(LEAK='Likely leak between pump discharge and tank inlet (outflow > inflow, pressure slightly low). Confirm with a walk-down and isolate the pipe section. Owner: maintenance engineer; operator reduces speed meanwhile.',
 BLOCKAGE='Likely blockage or partial closure (flow down, discharge pressure up). Check discharge valve position and strainers. Owner: operator, then maintenance.',
 PUMP_DEGRADATION='Pump efficiency loss (flow AND pressure falling together). Schedule vibration and impeller inspection; plan a swap. Owner: maintenance/quality engineer.',
 SENSOR_FAULT='Sensor fault, process looks healthy (cross-checks disagree while pressure and level stay consistent). Do not trip the process; verify and recalibrate the instrument. Owner: OT/IT administrator.',NORMAL='No action.')
def say(b):
  try:
    import anthropic
    r=anthropic.Anthropic().messages.create(model=os.getenv('CLAUDE_MODEL','claude-sonnet-4-6'),max_tokens=450,system='You are a plant-reliability copilot for operators and maintenance engineers. Under 150 words: likely cause, how to confirm, immediate action, owner. Never claim certainty; cite the evidence numbers.',messages=[{'role':'user','content':json.dumps(b,default=str)}])
    return r.content[0].text,'claude'
  except Exception: return PLAY.get(b.get('issue'),PLAY['NORMAL']),'playbook'
@app.get('/api/pumps')
def pumps(): return jsonify(q('select pump_id,facility_id,q_nom_m3h,shutoff_head_bar,dest_tank_id from pump order by pump_id'))
@app.get('/api/overview')
def overview():
  m=model(); w=m['windows']; cnt={t:q(f'select count(*) n from {t}')[0]['n'] for t in ['facility','pump','tank','valve','pipe','sensor','telemetry','alarm','simulation_run']}
  return jsonify(counts=cnt,metrics=m['metrics'],facilities=q('select * from facility'),mix=w.pred.value_counts().to_dict())
@app.get('/api/topology')
def topo():
  f=request.args.get('facility','FAC-001'); w=model()['windows']; w=w[w.facility_id==f]
  P={r['pump_id']:r for r in q('select * from pump where facility_id=%s',(f,))}; V={r['valve_id']:r for r in q('select * from valve where facility_id=%s',(f,))}; T={r['tank_id']:r for r in q('select * from tank where facility_id=%s',(f,))}
  pipes=q('select * from pipe where facility_id=%s order by serves_pump_id,seq',(f,)); health=w.sort_values('end_ts').groupby('pump_id').pred.last().to_dict()
  def node(i):
    if i in P: return dict(id=i,type='pump',health=health.get(i,'NORMAL'),sub=f"{P[i]['q_nom_m3h']:.0f} m³/h")
    if i in V: return dict(id=i,type='valve',health='NORMAL',sub=f"{V[i]['role'].lower()} {V[i]['open_pct']}%")
    return dict(id=i,type='tank',health='NORMAL',sub=f"{T[i]['capacity_m3']} m³") if i in T else dict(id=i,type='missing',health='NORMAL',sub='unknown')
  ch=[]
  for pid in P:
    ps=[x for x in pipes if x['serves_pump_id']==pid]; ch.append(dict(pump_id=pid,nodes=[node(ps[0]['from_node_id'])]+[node(x['to_node_id']) for x in ps]))
  return jsonify(chains=ch,invalid=[x for x in pipes if not x['serves_pump_id']])
@app.get('/api/series')
def series():
  pid=request.args['pump_id']; s=df("select sensor_id,measurand from sensor where pump_id=%s or sensor_id=(select s.sensor_id from sensor s join pump p on p.dest_tank_id=s.asset_id where p.pump_id=%s and s.measurand='LEVEL')",(pid,pid))
  t=df('select ts,sensor_id,value from telemetry where sensor_id in %s order by ts',(tuple(s.sensor_id),)).merge(s); w=t.pivot(index='ts',columns='measurand',values='value').reset_index()
  w['RESIDUAL']=w.FLOW-w.INLET_FLOW; w['t']=w.ts.map(fmt); d=model()['windows']; d=d[(d.pump_id==pid)&(d.pred!='NORMAL')]
  out=dict(data=w.drop(columns='ts').round(3).to_dict('records'),detections=[dict(x1=fmt(r.start_ts),x2=fmt(r.end_ts),pred=r.pred,conf=r.conf) for r in d.itertuples()])
  if request.args.get('eval'): g=df('select * from gt_events where pump_id=%s',(pid,)); out['truth']=[dict(x1=fmt(r.start_ts),x2=fmt(r.end_ts),issue=r.issue_type) for r in g.itertuples()]
  return jsonify(out)
@app.get('/api/detections')
def det():
  w=model()['windows']; f=request.args.get('facility'); w=w[(w.pred!='NORMAL')&((w.facility_id==f) if f else True)].sort_values('anomaly_score',ascending=False).head(150)
  return jsonify([dict(pump_id=r.pump_id,facility_id=r.facility_id,start=r.start_ts,end=r.end_ts,issue=r.pred,conf=r.conf,score=r.anomaly_score,evidence=r.evidence) for r in w.itertuples()])
@app.get('/api/alarms')
def alarms():
  w=model()['windows']; w=w[w.pred!='NORMAL']; g={k:v for k,v in w.groupby('pump_id')}; out=[]
  for r in df('select * from alarm order by raised_at desc limit 400').itertuples():
    ai='UNCONFIRMED'; x=g.get(r.pump_id)
    if x is not None:
      h=x[(x.start_ts<=r.cleared_at)&(x.end_ts>=r.raised_at)]
      if len(h): ai='SENSOR' if (h.pred=='SENSOR_FAULT').mean()>=.5 else 'PROCESS'
    out.append(dict(alarm_id=r.alarm_id,asset=r.asset_id,type=r.alarm_type,severity=r.severity,raised=r.raised_at,rule=r.alarm_category,ai=ai,mismatch=ai=='SENSOR'))
  return jsonify(out)
@app.get('/api/simulations')
def sims(): return jsonify([dict(r,config_json=json.loads(r['config_json']) if r['config_json'] else None,output_json=json.loads(r['output_json'])) for r in q('select * from simulation_run order by simulation_id desc limit 30')])
@app.post('/api/simulate')
def sim():
  b=request.get_json(force=True); p=q('select * from pump where pump_id=%s',(b['pump_id'],))[0]; cap=q('select capacity_m3 c from tank where tank_id=%s',(p['dest_tank_id'],))[0]['c']
  c={k:float(b.get(k,d)) for k,d in dict(speed=1,valve_open=1,leak=0,block=0,eff=1,duration_h=6).items()}; out=simulate(c,p,cap); dg=ml.diagnose(model(),p,c,out)
  sid=f"SIM-2026-{q('select count(*) n from simulation_run')[0]['n']+1:06d}"
  q('insert into simulation_run values(%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s)',(sid,p['facility_id'],p['pump_id'],b.get('scenario','WHAT_IF'),json.dumps(c),ASSUMPTIONS,json.dumps(out),20261022,'COMPLETED','API'))
  return jsonify(simulation_id=sid,config=c,output=out,diagnosis=dg)
@app.post('/api/copilot')
def copilot(): t,src=say(request.get_json(force=True)); return jsonify(text=t,source=src)
if __name__=='__main__': model(); app.run(port=5000)
