"""AI layer: physics-residual features -> RandomForest separating process faults from sensor faults. Ground truth is used ONLY as training/eval labels, never as a feature."""
import numpy as np,pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report,confusion_matrix
from physics import pump_state,mode_speed
W,STEP=12,6
F=['flow_ratio','pres_ratio','inlet_ratio','mb','mb_std','flow_std','inlet_std','pres_std','lvl_trend']
CLASSES=['NORMAL','LEAK','BLOCKAGE','PUMP_DEGRADATION','SENSOR_FAULT']
lab=lambda x:'SENSOR_FAULT' if x.startswith('SENSOR') else x
cat=lambda s:np.where(np.asarray(s)=='NORMAL','NONE',np.where(np.asarray(s)=='SENSOR_FAULT','SENSOR','PROCESS'))
def train(tel,sens,pumps,pv,events,seed=20261022):
  tel=tel.assign(ts=pd.to_datetime(tel.ts)); wide=tel.pivot(index='ts',columns='sensor_id',values='value').sort_index().dropna(); idx=wide.index
  vf=pv.assign(f=pv.open_pct/100).groupby('pump_id').f.prod(); spd=mode_speed(idx.hour.values)
  sid=lambda pid,m:sens[(sens.pump_id==pid)&(sens.measurand==m)].sensor_id.iloc[0]; lvl={r.asset_id:r.sensor_id for r in sens[sens.measurand=='LEVEL'].itertuples()}
  ev=events.assign(s=pd.to_datetime(events.start_ts),e=pd.to_datetime(events.end_ts)); rows=[]
  for p in pumps.itertuples():
    q,pr,qi=(wide[sid(p.pump_id,m)].values for m in ('FLOW','PRESSURE','INLET_FLOW')); Lv=wide[lvl[p.dest_tank_id]].values
    eq=p.q_nom_m3h*spd*vf[p.pump_id]; ep=pump_state(p.q_nom_m3h,p.shutoff_head_bar,spd,1,0,0,vf[p.pump_id])[1]; pe=ev[ev.pump_id==p.pump_id]
    for i in range(0,len(idx)-W+1,STEP):
      sl=slice(i,i+W); d=q[sl]-qi[sl]; y='NORMAL'
      for r in pe.itertuples():
        if ((idx[sl]>=r.s)&(idx[sl]<=r.e)).sum()>=W/2: y=lab(r.issue_type)
      rows.append(dict(pump_id=p.pump_id,facility_id=p.facility_id,start_ts=idx[i],end_ts=idx[i+W-1],true=y,flow_ratio=q[sl].mean()/eq[sl].mean(),pres_ratio=pr[sl].mean()/ep[sl].mean(),inlet_ratio=qi[sl].mean()/eq[sl].mean(),
        mb=d.mean()/p.q_nom_m3h,mb_std=d.std()/p.q_nom_m3h,flow_std=(q[sl]/eq[sl]).std(),inlet_std=(qi[sl]/eq[sl]).std(),pres_std=(pr[sl]/ep[sl]).std(),lvl_trend=(Lv[sl][-4:].mean()-Lv[sl][:4].mean())/.667))
  df=pd.DataFrame(rows); X=df[F]
  Xtr,Xte,ytr,yte,itr,ite=train_test_split(X,df.true,df.index,test_size=.3,stratify=df.true,random_state=seed)
  clf=RandomForestClassifier(300,class_weight='balanced',min_samples_leaf=2,random_state=seed,n_jobs=-1).fit(Xtr,ytr)
  cl=list(clf.classes_); Pm=clf.predict_proba(X); df['pred']=np.array(cl)[Pm.argmax(1)]; df['conf']=Pm.max(1).round(3); df['anomaly_score']=(1-Pm[:,cl.index('NORMAL')]).round(3)
  mu=X[df.true=='NORMAL'].mean(); sd=X[df.true=='NORMAL'].std()+1e-3; Z=(X-mu)/sd
  df['evidence']=[[dict(feature=f,value=round(float(X.iloc[i][f]),3),z=round(float(Z.iloc[i][f]),1)) for f in Z.iloc[i].abs().nlargest(3).index] if df.pred[i]!='NORMAL' else [] for i in range(len(df))]
  te=df.loc[ite]; an=te.true!='NORMAL'; rule=(te.mb.abs()>.06)|((te.pres_ratio-1).abs()>.15)|((te.flow_ratio-1).abs()>.2); rep=classification_report(yte,te.pred,output_dict=True,zero_division=0)
  summ=dict(detection_recall=float((te.pred[an]!='NORMAL').mean()),false_alarm_rate=float((te.pred[~an]!='NORMAL').mean()),category_accuracy=float((cat(te.pred[an])==cat(te.true[an])).mean()),macro_f1=float(rep['macro avg']['f1-score']),
    rule_recall=float(rule[an].mean()),rule_false_alarm=float(rule[~an].mean()),rule_category_accuracy=float((cat(te.true[an])=='PROCESS').mean()))
  return dict(windows=df,clf=clf,metrics=dict(summary=summ,matrix=dict(labels=CLASSES,values=confusion_matrix(te.true,te.pred,labels=CLASSES).tolist()),n_train=len(itr),n_test=len(ite),
    note='Stratified window split: adjacent windows are correlated, so scores are optimistic versus a time/asset hold-out. Rule baseline = 6% imbalance / 15% pressure / 20% flow thresholds, which labels every alarm PROCESS.'))
def diagnose(M,pump,cfg,out):
  qn,sp,vo=pump['q_nom_m3h'],cfg.get('speed',1),cfg.get('valve_open',1); eq=qn*sp*vo; ep=pump_state(qn,pump['shutoff_head_bar'],sp,1,0,0,vo)[1]
  f=dict(flow_ratio=out['flow_m3h']/eq,pres_ratio=out['pressure_bar']/ep,inlet_ratio=out['inlet_flow_m3h']/eq,mb=out['mass_balance_residual_m3h']/qn,mb_std=.005,flow_std=.01,inlet_std=.01,pres_std=.008,lvl_trend=out['level_rate_pct_per_h'])
  pr=M['clf'].predict_proba(pd.DataFrame([f])[F])[0]; return {c:round(float(v),3) for c,v in zip(M['clf'].classes_,pr)}
