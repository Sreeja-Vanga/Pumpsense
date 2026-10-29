"""Shared physics: used by the data generator, the ML feature builder and the live what-if simulator."""
import numpy as np
ASSUMPTIONS=("Steady-state affinity-law pump model: Q=Qnom*speed*eff*valve*(1-block); head P=P0*(speed*eff)^2*(1-0.25*(Q/Qnom)^2); "
 "leak removes a fraction of Q before the tank inlet and lowers P by 50% of that fraction; customer demand tracks the commanded flow; "
 "tank level rate=(Qin-demand)/capacity; units m3/h, bar, % of capacity; 6% flow-imbalance tolerance.")
def mode_speed(hour):
    h=np.asarray(hour); return np.where(((h>=6)&(h<10))|((h>=18)&(h<22)),1.15,np.where((h>=23)|(h<5),0.8,1.0))
MODES={1.15:'HIGH_DEMAND',0.8:'LOW_DEMAND',1.0:'NORMAL'}
def pump_state(qnom,p0,speed=1.0,eff=1.0,block=0.0,leak=0.0,valve=1.0):
    q=qnom*speed*eff*valve*(1-block)
    p=p0*(speed*eff)**2*(1-0.25*(q/qnom)**2)*(1-0.5*leak)
    return q,p,q*(1-leak)
def simulate(c,pump,cap):
    qn,p0=pump['q_nom_m3h'],pump['shutoff_head_bar']; sp,vo=c.get('speed',1),c.get('valve_open',1)
    q,p,qi=pump_state(qn,p0,sp,c.get('eff',1),c.get('block',0),c.get('leak',0),vo)
    eq=qn*sp*vo; ep=pump_state(qn,p0,sp,1,0,0,vo)[1]
    rate=(qi-eq)/cap*100; lvl=float(np.clip(50+rate*c.get('duration_h',6),0,100)); res=q-qi
    return dict(flow_m3h=round(float(q),2),pressure_bar=round(float(p),3),inlet_flow_m3h=round(float(qi),2),expected_flow_m3h=round(float(eq),2),
      mass_balance_residual_m3h=round(float(res),2),residual_pct_of_nominal=round(float(res/qn*100),2),level_rate_pct_per_h=round(float(rate),3),
      projected_level_pct=round(lvl,1),flags=dict(flow_imbalance=bool(abs(res)/qn>.06),pressure_out_of_band=bool(abs(p/ep-1)>.15),
      overflow_risk=bool(lvl>95),dry_run_risk=bool(lvl<5)))
