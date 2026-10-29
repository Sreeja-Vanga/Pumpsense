import {useEffect,useState} from 'react'
import {LineChart,Line,XAxis,YAxis,Tooltip,ResponsiveContainer,ReferenceArea,CartesianGrid} from 'recharts'
import './index.css'
const api=(p,o)=>fetch('/api'+p,o).then(r=>r.json())
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})
const NAV=['Overview','Flow diagram','Trends','Incidents','What-if','Alarm audit']
const COL={NORMAL:'var(--ok)',LEAK:'var(--blue)',BLOCKAGE:'var(--amber)',PUMP_DEGRADATION:'var(--rust)',SENSOR_FAULT:'var(--violet)'}
const NAMES={NORMAL:'Normal',LEAK:'Leak',BLOCKAGE:'Blockage',PUMP_DEGRADATION:'Pump degradation',SENSOR_FAULT:'Sensor fault'}
const pc=x=>(x*100).toFixed(1)+'%'
const Tag=({k})=><span className="tag" style={{'--c':COL[k]||'var(--mute)'}}>{NAMES[k]||k}</span>
const Loader=({msg='Loading from MySQL'})=><div className="loader"><i/><span>{msg}</span></div>
const Sym=({t})=>t==='tank'?<svg viewBox="0 0 40 30"><rect x="4" y="3" width="32" height="24" rx="2"/><path d="M4 15q5-4 8 0t8 0 8 0 8 0"/></svg>
 :t==='valve'?<svg viewBox="0 0 40 30"><path d="M5 5v20l15-10zM35 5v20L20 15z"/></svg>
 :t==='pump'?<svg viewBox="0 0 40 30"><circle cx="20" cy="15" r="11"/><path d="M20 4h14M14 10v10l11-5z"/></svg>:<svg viewBox="0 0 40 30"><path d="M6 6l28 18M34 6L6 24"/></svg>

export default function App(){
  const [tab,setTab]=useState('Overview'),[ov,setOv]=useState(null),[pumps,setPumps]=useState([]),[pump,setPump]=useState('PUMP-001'),[fac,setFac]=useState('FAC-001')
  useEffect(()=>{api('/pumps').then(setPumps);api('/overview').then(setOv)},[])
  const go=(t,p)=>{if(p)setPump(p);setTab(t)}
  const i=NAV.indexOf(tab)+1
  return <div className="sheet">
    <nav className="rail"><div className="brand"><svg viewBox="0 0 40 30"><circle cx="14" cy="15" r="9"/><path d="M14 6h22M9 10v10l10-5z"/></svg><b>PumpSense</b><small>Plant anomaly desk</small></div>
      {NAV.map((n,k)=><button key={n} className={n===tab?'on':''} onClick={()=>setTab(n)}><em>{k+1}</em>{n}</button>)}
      <div className="rail-foot">Synthetic data, seed 20261022. Ground truth is held out from the model.</div></nav>
    <main>
      <header className="title-block"><div><small>Sheet</small><b>{i} of {NAV.length}</b></div><div className="wide"><small>View</small><b>{tab}</b></div>
        <div><small>Facilities</small><b>{ov?ov.facilities.length:'…'}</b></div><div><small>Telemetry</small><b>{ov?ov.counts.telemetry.toLocaleString():'…'}</b></div><div><small>Model</small><b>RF-300 + Claude</b></div></header>
      {!ov?<Loader msg="Training the fault classifier on telemetry…"/>:<section key={tab} className="view">
        {tab==='Overview'&&<Overview ov={ov}/>}
        {tab==='Flow diagram'&&<Flow ov={ov} fac={fac} setFac={setFac} go={go}/>}
        {tab==='Trends'&&<Trends pumps={pumps} pump={pump} setPump={setPump}/>}
        {tab==='Incidents'&&<Incidents fac={fac} go={go}/>}
        {tab==='What-if'&&<WhatIf pumps={pumps} pump={pump} setPump={setPump}/>}
        {tab==='Alarm audit'&&<Alarms/>}</section>}
    </main></div>
}

function Overview({ov}){
  const s=ov.metrics.summary,m=ov.metrics.matrix,tot=Object.values(ov.mix).reduce((a,b)=>a+b,0)
  const Cmp=({l,ai,rule,low})=><div className="cmp"><span>{l}</span><div><i style={{width:ai*100+'%'}} className={low?'bad':'ai'}/><b>{pc(ai)}</b></div><div><i style={{width:rule*100+'%'}} className="rule"/><b>{pc(rule)}</b></div></div>
  return <>
    <h1>Can the plant tell a failing pump from a lying sensor?</h1>
    <p className="lede">Physics residuals (flow in versus flow out, pressure against the pump curve, tank level trend) feed a classifier. It is scored against a plain threshold rule engine on windows it never trained on.</p>
    <div className="stats">{Object.entries(ov.counts).map(([k,v])=><div key={k}><b>{v.toLocaleString()}</b><span>{k.replace('_',' ')}</span></div>)}</div>
    <div className="two">
      <div className="panel"><h3>Classifier against threshold rules</h3><div className="legend"><span><i className="ai"/>AI classifier</span><span><i className="rule"/>Rule engine</span></div>
        <Cmp l="Faults caught" ai={s.detection_recall} rule={s.rule_recall}/><Cmp l="Right cause (process vs sensor)" ai={s.category_accuracy} rule={s.rule_category_accuracy}/><Cmp l="False alarms on healthy windows" ai={s.false_alarm_rate} rule={s.rule_false_alarm} low/>
        <p className="note">{ov.metrics.note}</p></div>
      <div className="panel"><h3>Confusion matrix on held-out windows</h3><div className="matrix" style={{'--n':m.labels.length+1}}><span/>{m.labels.map(l=><em key={l}>{NAMES[l].split(' ')[0]}</em>)}
        {m.values.map((r,i)=>[<em key={'r'+i}>{NAMES[m.labels[i]].split(' ')[0]}</em>,...r.map((v,j)=><b key={i+'-'+j} className={i===j?'diag':v?'off':''} style={{'--a':v/Math.max(1,r.reduce((x,y)=>x+y,0))}}>{v}</b>)])}</div>
        <div className="mix">{Object.entries(ov.mix).map(([k,v])=><i key={k} title={`${NAMES[k]}: ${v}`} style={{flex:v,background:COL[k]}}/>)}</div><p className="note">Predicted mix across all {tot.toLocaleString()} one-hour windows. Rows are truth, columns are prediction.</p></div>
    </div></>
}

function Flow({ov,fac,setFac,go}){
  const [d,setD]=useState(null); useEffect(()=>{setD(null);api('/topology?facility='+fac).then(setD)},[fac])
  return <>
    <h1>Flow diagram</h1><p className="lede">Each line runs source tank, valves, pump, valves, destination tank. A pump takes the colour of the AI’s latest verdict; select it to open its trends.</p>
    <div className="tabs">{ov.facilities.map(f=><button key={f.facility_id} className={f.facility_id===fac?'on':''} onClick={()=>setFac(f.facility_id)}>{f.facility_id} {f.name}</button>)}</div>
    {!d?<Loader/>:<><div className="pid">{d.chains.map(c=><div className="line" key={c.pump_id}>{c.nodes.map((n,k)=><span className="seg" key={n.id+k}>{k>0&&<i className="pipe"/>}
      <button className={'node '+n.type} style={{'--c':COL[n.health]}} onClick={()=>n.type==='pump'&&go('Trends',n.id)}><Sym t={n.type}/><b>{n.id}</b><small>{n.sub}</small></button></span>)}</div>)}</div>
      {d.invalid.length>0&&<div className="callout"><b>{d.invalid.length} pipes point at assets that do not exist.</b> They are drawn in no line and are labelled edge cases in ground truth: {d.invalid.map(p=>`${p.pipe_id} (${p.from_node_id} to ${p.to_node_id})`).join(', ')}.</div>}</>}
  </>
}

function Chart({data,keys,det,truth,title,unit}){
  return <div className="panel chart"><h3>{title}<small>{unit}</small></h3><ResponsiveContainer width="100%" height={170}><LineChart data={data} margin={{left:-18,right:6,top:4}}>
    <CartesianGrid stroke="#10263d14" vertical={false}/><XAxis dataKey="t" tick={{fill:'#5a6b7d',fontSize:10}} minTickGap={60} stroke="#b8c4d0"/><YAxis tick={{fill:'#5a6b7d',fontSize:10}} domain={['auto','auto']} stroke="#b8c4d0"/>
    <Tooltip contentStyle={{background:'#fff',border:'1px solid #10263d',borderRadius:2,fontSize:12}}/>
    {det.map((a,i)=><ReferenceArea key={'d'+i} x1={a.x1} x2={a.x2} fill={COL[a.pred]} fillOpacity={.16} stroke="none"/>)}
    {(truth||[]).map((a,i)=><ReferenceArea key={'t'+i} x1={a.x1} x2={a.x2} fill="none" stroke="#10263d" strokeDasharray="4 3"/>)}
    {keys.map(k=><Line key={k[0]} dataKey={k[0]} name={k[2]||k[0]} stroke={k[1]} dot={false} strokeWidth={1.5} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>
}
const PumpPick=({pumps,pump,setPump})=><select value={pump} onChange={e=>setPump(e.target.value)}>{pumps.map(p=><option key={p.pump_id}>{p.pump_id}</option>)}</select>
function Trends({pumps,pump,setPump}){
  const [d,setD]=useState(null),[ev,setEv]=useState(false); useEffect(()=>{setD(null);api(`/series?pump_id=${pump}${ev?'&eval=1':''}`).then(setD)},[pump,ev])
  return <><h1>Trends</h1><p className="lede">Shaded bands are what the model flagged. Turn on the answer key to compare against the injected scenarios (dashed outlines).</p>
    <div className="bar"><PumpPick pumps={pumps} pump={pump} setPump={setPump}/><label className="sw"><input type="checkbox" checked={ev} onChange={e=>setEv(e.target.checked)}/>Show answer key</label></div>
    {!d?<Loader/>:<div className="charts">
      <Chart data={d.data} det={d.detections} truth={d.truth} title="Flow out of pump versus flow into tank" unit="m³/h" keys={[['FLOW','#0b7a75','Pump flow'],['INLET_FLOW','#1f6fd1','Tank inlet flow']]}/>
      <Chart data={d.data} det={d.detections} truth={d.truth} title="Mass-balance residual" unit="m³/h" keys={[['RESIDUAL','#c2410c','Flow out − flow in']]}/>
      <Chart data={d.data} det={d.detections} truth={d.truth} title="Discharge pressure" unit="bar" keys={[['PRESSURE','#10263d']]}/>
      <Chart data={d.data} det={d.detections} truth={d.truth} title="Destination tank level" unit="%" keys={[['LEVEL','#6b4fbb']]}/></div>}</>
}

function Incidents({fac,go}){
  const [rows,setRows]=useState(null),[sel,setSel]=useState(null),[ans,setAns]=useState(null),[busy,setBusy]=useState(false)
  useEffect(()=>{api('/detections?facility='+fac).then(setRows)},[fac])
  const ask=r=>{setSel(r);setAns(null);setBusy(true);post('/copilot',{pump_id:r.pump_id,issue:r.issue,confidence:r.conf,window:[r.start,r.end],evidence:r.evidence}).then(x=>{setAns(x);setBusy(false)})}
  return <><h1>Incidents in {fac}</h1><p className="lede">Ranked by anomaly score. Each row shows the residuals that drove the call. Ask the copilot for next steps.</p>
    <div className="split"><div className="panel tbl">{!rows?<Loader/>:<table><thead><tr><th>Pump</th><th>Window</th><th>Verdict</th><th>Conf.</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i} className={sel===r?'on':''} onClick={()=>ask(r)}>
      <td className="id">{r.pump_id}</td><td>{r.start.slice(5,16)}</td><td><Tag k={r.issue}/></td><td>{pc(r.conf)}</td></tr>)}</tbody></table>}</div>
      <aside className="panel">{!sel?<p className="empty">Pick an incident to see the evidence and a recommended response.</p>:<>
        <h3>{sel.pump_id}<Tag k={sel.issue}/></h3><ul className="ev">{sel.evidence.map(e=><li key={e.feature}><span>{e.feature.replace('_',' ')}</span><b>{e.value}</b><em>{e.z>0?'+':''}{e.z}σ</em></li>)}</ul>
        <div className="say">{busy?<Loader msg="Asking the copilot…"/>:<><small>Source: {ans?.source==='claude'?'Claude':'built-in playbook (set ANTHROPIC_API_KEY for Claude)'}</small><p>{ans?.text}</p></>}</div>
        <button className="btn ghost" onClick={()=>go('Trends',sel.pump_id)}>Open trends for {sel.pump_id}</button></>}</aside></div></>
}

const SL=[['speed','Pump speed',.5,1.3,.01,'×'],['valve_open','Valve opening',.3,1,.01,'×'],['leak','Leak fraction',0,.5,.01,''],['block','Blockage',0,.7,.01,''],['eff','Pump efficiency',.5,1,.01,'×'],['duration_h','Horizon',1,24,1,'h']]
function WhatIf({pumps,pump,setPump}){
  const [c,setC]=useState({speed:1,valve_open:1,leak:0,block:0,eff:1,duration_h:6}),[r,setR]=useState(null),[h,setH]=useState([])
  const hist=()=>api('/simulations').then(setH); useEffect(()=>{hist()},[])
  const run=()=>post('/simulate',{pump_id:pump,...c}).then(x=>{setR(x);hist()}); const o=r?.output
  return <><h1>What-if simulator</h1><p className="lede">Change the operating point, run the same physics the data was generated with, and let the classifier say what it would look like in telemetry. Every run is stored with its inputs.</p>
    <div className="split"><div className="panel"><div className="bar"><PumpPick pumps={pumps} pump={pump} setPump={setPump}/></div>
      {SL.map(([k,l,a,b,s,u])=><label className="sl" key={k}><span>{l}</span><input type="range" min={a} max={b} step={s} value={c[k]} onChange={e=>setC({...c,[k]:+e.target.value})}/><b>{c[k]}{u}</b></label>)}
      <button className="btn" onClick={run}>Run simulation</button></div>
      <div className="panel">{!o?<p className="empty">Results appear here.</p>:<><h3>{r.simulation_id}</h3><div className="res">
        {[['Pump flow',o.flow_m3h,'m³/h'],['Tank inlet',o.inlet_flow_m3h,'m³/h'],['Residual',o.mass_balance_residual_m3h,'m³/h'],['Pressure',o.pressure_bar,'bar'],['Level in '+c.duration_h+'h',o.projected_level_pct,'%']].map(([a,b,u])=><div key={a}><span>{a}</span><b>{b}<small>{u}</small></b></div>)}</div>
        <div className="flags">{Object.entries(o.flags).map(([k,v])=><span key={k} className={v?'f on':'f'}>{k.replaceAll('_',' ')}</span>)}</div>
        <h4>Classifier reading</h4>{Object.entries(r.diagnosis).sort((a,b)=>b[1]-a[1]).map(([k,v])=><div className="prob" key={k}><span>{NAMES[k]}</span><i style={{width:v*100+'%',background:COL[k]}}/><b>{pc(v)}</b></div>)}</>}</div></div>
    <div className="panel tbl"><h3>Run history</h3><table><thead><tr><th>ID</th><th>Pump</th><th>Scenario</th><th>Inputs</th><th>Residual</th></tr></thead><tbody>{h.map(x=><tr key={x.simulation_id}><td className="id">{x.simulation_id}</td><td>{x.pump_id}</td><td>{x.scenario_type.replaceAll('_',' ').toLowerCase()}</td>
      <td>{x.config_json?Object.entries(x.config_json).filter(([k,v])=>v!==(k==='eff'||k==='speed'?1:0)&&k!=='duration_h').map(([k,v])=>`${k} ${v}`).join(', ')||'nominal':<span className="miss">config missing</span>}</td><td>{x.output_json.mass_balance_residual_m3h} m³/h</td></tr>)}</tbody></table></div></>
}

function Alarms(){
  const [a,setA]=useState(null); useEffect(()=>{api('/alarms').then(setA)},[])
  const mm=a?.filter(x=>x.mismatch).length
  return <><h1>Alarm audit</h1><p className="lede">The plant’s rule engine files every alarm as a process alarm. Here the classifier re-reads each one against the telemetry around it.</p>
    {!a?<Loader/>:<><div className="callout"><b>{mm} of {a.length} recent alarms look like instrument faults, not process faults.</b> Tripping the process on these would cause an avoidable shutdown.</div>
      <div className="panel tbl"><table><thead><tr><th>Alarm</th><th>Asset</th><th>Type</th><th>Raised</th><th>Rule engine</th><th>AI reading</th></tr></thead><tbody>{a.map(x=><tr key={x.alarm_id} className={x.mismatch?'flag':''}><td className="id">{x.alarm_id}</td><td className="id">{x.asset}</td><td>{x.type.replaceAll('_',' ').toLowerCase()}</td><td>{x.raised.slice(5,16)}</td><td>{x.rule.toLowerCase()}</td>
        <td><span className="tag" style={{'--c':x.ai==='SENSOR'?'var(--violet)':x.ai==='PROCESS'?'var(--blue)':'var(--mute)'}}>{x.ai.toLowerCase()}</span></td></tr>)}</tbody></table></div></>}</>
}
