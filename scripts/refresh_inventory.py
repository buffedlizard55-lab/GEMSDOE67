import concurrent.futures,subprocess,json,datetime
names=['GEMSDOE','6GEMSDOE','5GEMSDOE','7GEMSDOE','8GEMSDOE','11GEMSDOE','12GEMSDOE','15GEMSDOE','14GEMSDOE','17GEMSDOE','18GEMSDOE','19GEMSDOE','13GEMSDOE','16GEMSDOE','20GEMSDOE']+['GEMSDOE'+str(i) for i in list(range(2,5))+[9,10]+list(range(21,55))+list(range(63,66))]+[str(i)+'GEMSDOE' for i in range(55,63)]+['GEMSDOE'+str(i) for i in range(66,73)]
def run(name):
 p=subprocess.run(['gh','api',f'repos/buffedlizard55-lab/{name}/git/trees/HEAD?recursive=1'],capture_output=True,text=True)
 if p.returncode: return {'repo':name,'status':'unavailable','error':p.stderr.strip()}
 j=json.loads(p.stdout); paths=[x['path'] for x in j.get('tree',[])]; matches=[p for p in paths if any(s in p.lower() for s in ['evaluate_holdout','submission_writer','validate_submission','feature_stack','registry','receipt'])]; rasters=[{'path':x['path'],'bytes':x.get('size'),'blob_sha':x['sha']} for x in j.get('tree',[]) if x['path'].lower().endswith(('.tif','.tiff','.npz'))]
 return {'repo':name,'status':'tree_read','commit_tree':j['sha'],'truncated':j.get('truncated'),'shared_tool_candidates':matches,'rasters':rasters}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: rows=list(ex.map(run,dict.fromkeys(names)))
json.dump({'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GitHub API HEAD tree inventory; not website/score verification','repositories':rows},open('evidence/repository_inventory.json','w'),indent=2)
for r in rows:
 print(r['repo'],r['status'],len(r.get('rasters',[])),[p for p in r.get('shared_tool_candidates',[]) if any(s in p for s in ['evaluate_holdout','submission_writer','feature_stack'])])
