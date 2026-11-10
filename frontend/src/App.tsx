import {useEffect,useState} from 'react';
import {MapContainer,TileLayer,Marker,Popup,Polyline,CircleMarker} from 'react-leaflet';
import L from 'leaflet';
const API='http://127.0.0.1:8000';
type Building={id:string;name:string;risk_level:string;lat:number;lng:number;verified:boolean};
type Incident={id:string;incident_type:string;severity:string;title:string;lat:number;lng:number;status:string;created_at:string};
const icon=L.divIcon({className:'building-pin',html:'▰',iconSize:[20,20]});
export default function App(){
 const [buildings,setBuildings]=useState<Building[]>([]),[incidents,setIncidents]=useState<Incident[]>([]),[readings,setReadings]=useState<any[]>([]),[message,setMessage]=useState('');
 async function refresh(){try{const [b,i,r]=await Promise.all([fetch(API+'/api/buildings').then(x=>x.json()),fetch(API+'/api/incidents').then(x=>x.json()),fetch(API+'/api/readings').then(x=>x.json())]);setBuildings(b);setIncidents(i);setReadings(r);setMessage('API connected')}catch{setMessage('API offline — start FastAPI on port 8000')}}
 useEffect(()=>{refresh();const t=setInterval(refresh,3000);return()=>clearInterval(t)},[]);
 async function tick(){await fetch(API+'/api/simulation/tick',{method:'POST'});await refresh()}
 const riskColor=(r:string)=>r==='high'?'#ef4444':r==='medium'?'#f59e0b':'#22c55e';
 return <div className="app">
  <header><div><div className="brand">JURAS <span>URBAN RISK INTELLIGENCE</span></div><small>PURANI MANDI · PROTOTYPE DASHBOARD</small></div><div className="status">● {message}</div></header>
  <nav><span className="active">Overview</span><span>Living Map</span><span>Fire & Safety</span><span>Structural</span><span>Stormwater</span></nav>
  <main><div className="kpis"><div><small>Mapped demo buildings</small><b>{buildings.length}</b></div><div><small>Active incidents</small><b>{incidents.filter(i=>i.status==='active').length}</b></div><div><small>Latest sensor samples</small><b>{readings.length}</b></div><div><small>Data mode</small><b className="sim">SIMULATION</b></div></div>
  <section className="content"><div className="mapbox"><div className="maptitle">Purani Mandi · Live risk map <small>Illustrative demo coordinates — verify before field use</small></div>
   <MapContainer center={[32.7350,74.8620]} zoom={16} style={{height:'100%',minHeight:480}}><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
   {buildings.map(b=><Marker key={b.id} position={[b.lat,b.lng]} icon={icon}><Popup><b>{b.name}</b><br/>{b.id}<br/>Risk: {b.risk_level}<br/>Data verified: {String(b.verified)}</Popup></Marker>)}
   {incidents.map(i=><CircleMarker key={i.id} center={[i.lat,i.lng]} radius={10} pathOptions={{color:riskColor(i.severity),fillOpacity:.7}}><Popup>{i.title}<br/>Severity: {i.severity}<br/>Status: {i.status}</Popup></CircleMarker>)}
   <Polyline positions={[[32.7342,74.8610],[32.7347,74.8620],[32.7350,74.8632]]} pathOptions={{color:'#2563eb',weight:5,dashArray:'8 8'}}/>
   </MapContainer><div className="legend">🟢 Low &nbsp; 🟠 Medium &nbsp; 🔴 High &nbsp; ━ Demo route</div></div>
   <aside><div className="panel"><h3>Prototype controls</h3><p>Generate one simulated sensor cycle. Random values are clearly labeled simulation.</p><button onClick={tick}>▶ Run sensor simulation</button><button className="secondary" onClick={refresh}>↻ Refresh dashboard</button></div>
   <div className="panel"><h3>Recent incidents</h3>{incidents.slice(-5).reverse().map(i=><div className="incident" key={i.id}><strong style={{color:riskColor(i.severity)}}>● {i.severity.toUpperCase()}</strong><p>{i.title}</p><small>{i.id} · {i.status}</small></div>)}{!incidents.length&&<p className="muted">No incidents. Run simulation.</p>}</div>
   <div className="panel"><h3>Latest readings</h3>{readings.slice(-5).reverse().map((r,i)=><div className="reading" key={i}><span>{r.metric}</span><b>{r.value} {r.unit}</b><small>{r.mode}</small></div>)}</div></aside></section>
  <footer>JURAS MVP · Simulation data is not a real sensor measurement or verified municipal dataset.</footer></main></div>
}
