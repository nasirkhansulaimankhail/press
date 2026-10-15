"""Check split tool runtimes using local playbooks and a local Semgrep rule."""
from pathlib import Path
import json,os,subprocess,sys
b=Path(sys.argv[1]).resolve();assert (b/'sites/press-helpdesk.localhost').is_dir()
out=b/'staging/dependency-tool-checks';out.mkdir(exist_ok=True)
legacy=b/'staging/tools/ansible-runner/env/bin/python'
semgrep=b/'staging/tools/semgrep/env/bin/semgrep'
root=b/'apps/press'
env=os.environ.copy();env.update(PYTHONPATH=str(b/'staging/guard'),OBJC_DISABLE_INITIALIZE_FORK_SAFETY='YES',ANSIBLE_LOCAL_TEMP=str(out/'ansible-local'),ANSIBLE_REMOTE_TEMP=str(out/'ansible-remote'),ANSIBLE_RETRY_FILES_ENABLED='False',SEMGREP_ENABLE_VERSION_CHECK='0',SEMGREP_SEND_METRICS='off')
results={}
for name,python in [('ansible',legacy),('semgrep',semgrep.parent/'python')]:
 r=subprocess.run([str(python),'-m','pip','check'],env=env,capture_output=True,text=True)
 (out/(name+'-pip-check.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,name
 results[name+'_dependencies']='passed'
role=out/'roles/contract/tasks';role.mkdir(parents=True,exist_ok=True)
(role/'main.yml').write_text('''- name: Assert local variable contract
  assert:
    that: stage_marker == 'local-only'
- name: Local asynchronous operation
  command:
    argv:
      - "{{ stage_python }}"
      - -c
      - "print('local-async-contract')"
  async: 10
  poll: 1
- name: Emit local result
  debug:
    msg: local-only
''')
playbook=out/'local.yml';playbook.write_text('''- name: Local bridge contract
  hosts: all
  connection: local
  gather_facts: false
  roles:
    - contract
''')
variables={'stage_marker':'local-only','stage_python':str(legacy),'ansible_python_interpreter':str(legacy),'ansible_async_dir':str(out/'async')}
varsfile=out/'vars.json';varsfile.write_text(json.dumps(variables))
base=[str(legacy),str(root/'press/scripts/ansible_bridge.py')]
args=['--playbook',str(playbook),'--host','localhost','--port','22','--user',os.environ.get('USER','nasir'),'--extra-vars-file',str(varsfile)]
r=subprocess.run(base+['inspect']+args,env=env,capture_output=True,text=True)
(out/'ansible-inspect.log').write_text(r.stdout+r.stderr);assert r.returncode==0,'Ansible inspect'
assert len(json.loads(r.stdout)['tasks'])==3
r=subprocess.run(base+['run']+args,env=env,capture_output=True,text=True)
(out/'ansible-local-run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,'Ansible local run'
events=[]
for line in r.stdout.splitlines():
 try:events.append(json.loads(line))
 except ValueError:pass
assert any(e['event']=='play_stats' and e['stats']['ok']==3 for e in events)
assert any(e['event']=='async_start' for e in events)
assert any(e['event']=='async_poll' for e in events)
results['ansible_inspect_local_success_async_events']='passed'
(role/'main.yml').write_text('- name: Expected local failure\n  assert:\n    that: false\n')
r=subprocess.run(base+['run']+args,env=env,capture_output=True,text=True)
(out/'ansible-expected-failure.log').write_text(r.stdout+r.stderr);assert r.returncode!=0
assert any('"status": "Failure"' in line for line in r.stdout.splitlines())
results['ansible_failure_propagation']='passed'
rule=out/'rule.yml';rule.write_text('''rules:
- id: staging-eval
  languages: [python]
  message: Synthetic local rule
  severity: ERROR
  pattern: eval(...)
''')
sample=out/'sample.py';sample.write_text('eval("local-only")\n')
cmd=[str(semgrep),'scan','--metrics=off','--disable-version-check','--config',str(rule),'--json','--quiet',str(sample)]
r=subprocess.run(cmd,env=env,cwd=out,capture_output=True,text=True)
(out/'semgrep-scan.log').write_text(r.stdout+r.stderr);assert r.returncode in (0,1),r.returncode
scan=json.loads(r.stdout);assert len(scan['results'])==1
assert scan['results'][0]['check_id'].endswith('staging-eval')
results['semgrep_local_rule_finding']='passed'
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
