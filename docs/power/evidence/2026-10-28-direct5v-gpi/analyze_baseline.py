"""Offline native-sample phase and energy analysis; never accesses hardware."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
import numpy as np

BASE=Path(__file__).resolve().parent
FS=2000000
EVENTS={1:'receiver_entry',2:'first_strobe_irq_observed',3:'first_frame_complete_irq_observed',
4:'sd_initialization_begin',5:'sd_initialization_complete',6:'first_payload_submission',
7:'padded_payload_ready',8:'full_slot_commit_complete',9:'sd_deinitialization_complete',10:'pre_standby_wfi'}
PRECEDENCE=((1,2),(2,3),(1,4),(4,5),(5,6),(6,7),(3,7),(7,8),(8,9),(9,10))

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def analyze(folder):
 result=json.loads((folder/'result.json').read_text());assert result['success']
 rows=[json.loads(s) for s in (folder/'chunks.jsonl').read_text().splitlines()]
 signals={};checks={}
 for s in ['current','voltage','power','gpi0','gpi1']:
  rs=[r for r in rows if r['signal']==s];digital=s.startswith('gpi')
  path=folder/(s+('.u1' if digital else '.f32'))
  assert digest(path)==result['sha256'][s],s+' hash'
  data=np.memmap(path,mode='r',dtype='u1' if digital else '<f4')
  issues=[];previous_offset=0;lengths=[]
  for i,r in enumerate(rs):
   assert r['sample_rate']==FS and r['decimate_factor']==1
   assert r['byte_offset']==previous_offset
   previous_offset+=r['byte_count']
   n=r['byte_count']*(8 if digital else .25);assert n==int(n);n=int(n)
   if i+1<len(rs):
    step=rs[i+1]['sample_id']-r['sample_id']
    if digital:
     if not 0<=n-step<=7:issues.append([i,step,n])
     n=step
    elif step!=n:issues.append([i,step,n])
   elif digital:
    # The binding omits element_count. Last chunk's valid endpoint is unresolved.
    n=0
   lengths.append(n)
  assert not issues,(s,issues)
  if digital:
   parts=[]
   for r,n in zip(rs,lengths):
    parts.append(np.unpackbits(data[r['byte_offset']:r['byte_offset']+r['byte_count']],bitorder='little')[:n])
   values=np.concatenate(parts)
  else:values=data
  start=rs[0]['sample_id'];signals[s]=(start,values)
  checks[s]={'sha256':result['sha256'][s],'contiguous':True,'first_sample_id':start,
             'analyzed_end_exclusive':start+len(values),'chunks':len(rs),
             'nonfinite_samples':None if digital else int(np.count_nonzero(~np.isfinite(values))),
             'last_digital_chunk_excluded':digital}
  if digital:
   edges=np.flatnonzero(values[1:]!=values[:-1])+1
   er=[{'sample_id':int(x+start),'level':int(values[x])} for x in edges]
   groups=[]
   for e in er:
    if not groups or e['sample_id']-groups[-1][-1]['sample_id']>2000:groups.append([])
    groups[-1].append(e)
   checks[s]['initial_level']=int(values[0]);checks[s]['edge_count']=len(er)
   checks[s]['edge_groups']=[{'start_sample_id':g[0]['sample_id'],'end_sample_id':g[-1]['sample_id'],
                             'edges':len(g),'first_level':g[0]['level'],'last_level':g[-1]['level']} for g in groups]
   signals[s+'_edges']=er

 # Separate dense, unconfigured startup chatter from low-rate firmware events.
 # Candidate marker train must contain exactly one of each ID and obey semantics.
 # Width acceptance explicitly includes 0.5 us grid quantization and known ~0.24 us hook overhead.
 edges=signals['gpi0_edges'];pulses=[]
 for a,b in zip(edges,edges[1:]):
  if a['level']==1 and b['level']==0:
   width=(b['sample_id']-a['sample_id'])/2
   matches=[i for i in EVENTS if abs(width-(2*i+.24))<=.75]
   pulses.append({'start_sample_id':a['sample_id'],'end_sample_id':b['sample_id'],
                  'width_us':width,'matching_ids':matches})
 candidates=[]
 for i,p in enumerate(pulses):
  if p['matching_ids']!=[1]:continue
  train=pulses[i:i+10]
  if len(train)!=10 or any(len(q['matching_ids'])!=1 for q in train):continue
  ids=[q['matching_ids'][0] for q in train]
  if sorted(ids)!=list(range(1,11)):continue
  by={q['matching_ids'][0]:q for q in train}
  if all(by[a]['start_sample_id']<by[b]['start_sample_id'] for a,b in PRECEDENCE):candidates.append(train)
 assert len(candidates)==1,('ambiguous/missing train',len(candidates))
 train=candidates[0];marker={p['matching_ids'][0]:p for p in train}
 current_start,current=signals['current'];first=marker[1]['start_sample_id']
 search_begin=max(current_start,first-int(.5*FS));search_end=first
 segment=current[search_begin-current_start:search_end-current_start]
 crossings=np.flatnonzero(segment>=.020)
 assert len(crossings)
 onset=search_begin+int(crossings[0])
 before=current[onset-current_start-2000:onset-current_start]
 assert np.all(np.isfinite(before)) and abs(float(np.mean(before)))<.0001
 wfi=marker[10]['start_sample_id'];wfi_end=marker[10]['end_sample_id']
 # First whole 1 ms bin after WFI whose following ten bins are in 6..12 mA.
 bin0=((wfi_end+1999)//2000)*2000
 stop=min(bin0+int(2*FS),current_start+len(current));nb=(stop-bin0)//2000
 bins=current[bin0-current_start:bin0-current_start+nb*2000].reshape(nb,2000).mean(axis=1,dtype=np.float64)
 good=(bins>.006)&(bins<.012)
 candidates=np.flatnonzero(np.convolve(good.astype(int),np.ones(10,dtype=int),'valid')==10)
 assert len(candidates)
 plateau=bin0+int(candidates[0])*2000

 def window(a,b):
  out={'start_sample_id':int(a),'end_sample_id_exclusive':int(b),'duration_ms':(b-a)/FS*1000}
  for s in ['current','voltage','power']:
   st,v=signals[s];x=v[a-st:b-st]
   assert len(x)==b-a and np.all(np.isfinite(x)),(s,a,b)
   out[s+'_mean']=float(np.mean(x,dtype=np.float64));out[s+'_min']=float(np.min(x));out[s+'_max']=float(np.max(x))
   if s=='power':out['energy_mJ']=float(np.sum(x,dtype=np.float64)/FS*1000)
  # 1 ms nonoverlapping bins, aligned at this window's start; omit partial tail.
  st,v=signals['current'];x=v[a-st:b-st];n=len(x)//2000
  out['max_1ms_mean_current_mA']=float(np.max(x[:n*2000].reshape(n,2000).mean(axis=1,dtype=np.float64))*1000) if n else None
  out['all_samples_finite']=True
  return out

 events=[]
 for p in train:
  i=p['matching_ids'][0]
  events.append({'id':i,'name':EVENTS[i],'sample_id':p['start_sample_id'],
                 'time_since_current_onset_ms':(p['start_sample_id']-onset)/FS*1000,
                 'width_us':p['width_us']})
 intervals={name:window(marker[a]['start_sample_id'],marker[b]['start_sample_id']) for name,a,b in [
  ('receiver_to_strobe',1,2),('strobe_to_frame_complete',2,3),('sd_init',4,5),
  ('sd_ready_to_first_payload',5,6),('first_payload_to_commit',6,8),('commit_to_pre_wfi',8,10)]}
 overlap=max(0,min(marker[3]['start_sample_id'],marker[5]['start_sample_id'])-max(marker[2]['start_sample_id'],marker[4]['start_sample_id']))/FS*1000
 report={'run':folder.name,'recording_closed_utc':result['utc'],'sample_rate':FS,'sample_grid_us':.5,
  'checks':checks,'whole_session_all_analog_finite':all(checks[s]['nonfinite_samples']==0 for s in ('current','voltage','power')),
  'marker_decode':{'ids':[e['id'] for e in events],'precedence_pass':True,'unique_train':True,
    'width_rule':'abs(width_us - (2*ID + 0.24)) <= 0.75; IDs separated by 2 us; not inherited Saleae tolerance',
    'unclassified_pulses':len(pulses)-10,
    'unclassified_pulse_records':[p for p in pulses if p not in train],
    'events':events},
  'current_onset':{'sample_id':onset,'definition':'first >=20 mA sample in 500 ms before receiver marker; preceding 1 ms mean absolute <100 uA'},
  'onset_to_pre_wfi':window(onset,wfi),'onset_to_low_plateau':window(onset,plateau),
  'startup_first_5ms':window(onset,onset+10000),
  'after_first_5ms_to_pre_wfi':window(onset+10000,wfi),
  'after_first_5ms_to_low_plateau':window(onset+10000,plateau),
  'low_plateau':window(plateau,plateau+int(.1*FS)),
  'plateau_definition':'first whole 1 ms bin after pre-WFI pulse with 10 consecutive bin means in 6..12 mA; endpoint resolution 1 ms',
  'intervals':intervals,'sd_init_overlaps_strobe_to_frame_ms':overlap,
  'whole_cycle_energy_qualified':False,
  'energy_qualification':'Onset-based whole-cycle and first-5-ms numbers are provisional raw integrals; startup instantaneous current/voltage magnitude is not independently qualified. The separately reported post-5-ms interval is finite and contiguous with source voltage approximately 4.93..5.03 V; it excludes startup energy and is not a full-cycle or image-integrity qualification.',
  'limits':['Digital markers indicate firmware observations, not independent SD readback or Standby flags.',
            'PD0 startup chatter/high level is not separately qualified as exact reset or firmware-entry timing.',
            'JS voltage is input-side; current range and wiring drop are not included in target voltage.',
            'Native instantaneous peak is retained but not independently qualified against range-transition/clipping effects.',
            'Power includes board overhead; 13-bit analog with GPIO enabled; no battery/LTC conversion.']}
 (folder/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
 (folder/'all-gpio-edges.json').write_text(json.dumps({s:signals[s+'_edges'] for s in ['gpi0','gpi1']},indent=2)+'\n')
 with (folder/'phase-events.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(events[0]));w.writeheader();w.writerows(events)
 # Compact 1 ms profile for export and graphing, retain mean/min/max.
 lo=max(current_start,onset-10000);hi=plateau+int(.05*FS);n=(hi-lo)//2000
 profile=[]
 for k in range(n):
  a=lo+k*2000;b=a+2000;st,x=signals['current'];seg=x[a-st:b-st]
  vs,v=signals['voltage'];vv=v[a-vs:b-vs]
  profile.append({'time_ms':((a+b)/2-onset)/FS*1000,'current_mean_mA':float(np.mean(seg,dtype=np.float64)*1000),
                  'current_min_mA':float(np.min(seg)*1000),'current_max_mA':float(np.max(seg)*1000),
                  'voltage_mean_V':float(np.mean(vv,dtype=np.float64))})
 with (folder/'profile-1ms.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(profile[0]));w.writeheader();w.writerows(profile)
 return report

def main():
 ap=argparse.ArgumentParser();ap.add_argument('runs',nargs='*',default=['cold01','cold02','cold03']);a=ap.parse_args()
 reports=[]
 for name in a.runs:
  folder=BASE/name
  if not (folder/'result.json').exists():continue
  r=analyze(folder);reports.append(r)
  print(json.dumps({'run':name,'phases':r['marker_decode']['events'],'pre_wfi':r['onset_to_pre_wfi'],
                    'low_plateau':r['low_plateau'],'plateau_window':r['onset_to_low_plateau']}))
 (BASE/'baseline-analysis.json').write_text(json.dumps(reports,indent=2)+'\n')
 return 0
if __name__=='__main__':raise SystemExit(main())
