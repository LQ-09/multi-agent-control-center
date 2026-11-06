"""Task-specific staffing, with explicit scope and evidence-based delivery."""
import json
import re

def prompt(step):
    task=step['task']
    if step['role']=='Plan':
        return ('Choose the smallest useful team for this task from the numbered available configurations below. '
            'You may reuse a configuration for multiple assignments; independent review is optional when warranted. '
            'Plan a dependency DAG on this host: independent assignments run concurrently (up to 3). '
            'Declare only real dependencies; a join waits for its dependencies, not unrelated branches. '
            'Use read-only for research/analysis; workspace-write only for necessary Codex file edits. '
            'Shared workspace writes are exclusive. Use isolated browser sessions for independent research, '
            'shared only when an existing ACC login is necessary (shared browser assignments are serialized). '
            'For a simple task use one Deliver assignment that does the work and checks its own result. '
            'For a larger task use Execute assignments, optional Review assignments, then exactly one final Deliver. '
            'Return <acc_plan>{"steps":[{"id":"research_a","depends_on":[],"access":"read-only|workspace-write","browser":"isolated|shared","role":"Execute|Review|Deliver","slot":0,"instruction":"specific responsibility and evidence required"}]}</acc_plan> '
            'with 1–24 assignments and unique IDs. Dependencies reference IDs in this plan. No cycles. '
            'Exactly one Deliver must depend transitively on every assignment, to integrate and check all evidence. Only Codex Execute or Deliver can edit files, '
            'and only when this task has workspace-write permission. Generate <acceptance_criteria>checkable criteria</acceptance_criteria> '
            'if none were provided. Finish with a succeeded acc_result when the plan is ready. Task maximum file permission: '+task['execution_mode']+'. Available configurations: '+task['agent_pool'])
    return ('Your assignment: '+step.get('instruction','')+'. Execute only this assignment; previous results are supplied below. '
            'For Review use failed with concrete feedback when changes are required. '
            'For Deliver, complete any assigned work, integrate previous findings and verify the task acceptance criteria. '
            'For failed Review/Deliver, include rework_ids listing the upstream node IDs requiring fixes. '
            'Deliver may instead emit a new acc_plan with additional dependency-based assignments and a final Deliver '
            '(same schema as the original plan, dependencies within the new plan), plus a succeeded result with accepted:false. '
            'This schedules a follow-up round using all prior evidence, up to 3 rounds. '
            'Only Deliver may declare the whole task complete. A final Deliver without a follow-up plan MUST include "accepted":true '
            'and evidence for all acceptance criteria in details. Missing evidence is failed or blocked, never accepted. '
            'Do not require an extra reviewer unless the task itself requires one.')

def plan_steps(output, pool):
    matches=re.findall(r'<acc_plan>(.*?)</acc_plan>',output,re.S)
    if len(matches)!=1: raise ValueError('Planner must return exactly one acc_plan.')
    value=json.loads(matches[0])
    if not isinstance(value,dict): raise ValueError('acc_plan must be an object.')
    rows=value.get('steps')
    if not isinstance(rows,list) or not 1<=len(rows)<=24: raise ValueError('Plan needs 1–24 assignments.')
    for i,row in enumerate(rows):
        if not isinstance(row,dict) or row.get('role') not in ('Execute','Review','Deliver'):
            raise ValueError('Unsupported assignment role.')
        slot=row.get('slot')
        if type(slot) is not int or not 0<=slot<len(pool): raise ValueError('Plan selected an unavailable agent configuration.')
        if not isinstance(row.get('instruction'),str) or not 1<=len(row['instruction'].strip())<=4000:
            raise ValueError('Each assignment needs a concrete instruction (1–4000 characters).')
        if (row['role']=='Deliver') != (i==len(rows)-1): raise ValueError('Exactly the last assignment must deliver.')
    explicit = any('id' in r or 'depends_on' in r for r in rows)
    for i,row in enumerate(rows):
        if explicit:
            if not isinstance(row.get('id'),str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}',row['id']):
                raise ValueError('Graph nodes require short unique IDs.')
            deps=row.get('depends_on')
            if not isinstance(deps,list) or any(not isinstance(x,str) for x in deps):
                raise ValueError('Each graph node requires depends_on IDs.')
        else:
            row['id']='step_'+str(i+1)
            row['depends_on']=[rows[i-1]['id']] if i else []
        row.setdefault('access','read-only' if explicit else '')
        row.setdefault('browser','isolated' if explicit else 'shared')
        if row['access'] not in ('','read-only','workspace-write') or row['browser'] not in ('isolated','shared'):
            raise ValueError('Unsupported workspace access or browser ownership.')
        if row['access']=='workspace-write' and (pool[row['slot']]['agent']!='codex' or row['role'] not in ('Execute','Deliver')):
            raise ValueError('Only Codex execution or delivery can write.')
    by_id={r['id']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('Duplicate graph node ID.')
    ordered=[];seen=set()
    while len(ordered)<len(rows):
        ready=[r for r in rows if r['id'] not in seen and set(r['depends_on'])<=seen]
        if not ready:raise ValueError('Graph has a cycle or an unknown dependency.')
        ordered.extend(ready);seen.update(r['id'] for r in ready)
    final=rows[-1];reach=set()
    def visit(ident):
        for dep in by_id[ident]['depends_on']:
            if dep not in reach:reach.add(dep);visit(dep)
    visit(final['id'])
    if reach != set(by_id)-{final['id']}:raise ValueError('Deliver must join all assignments.')
    return ordered

def finish(store, step, output, error, stopped):
    from core import clean, digest, now, uid, result_contract
    task=store.get_task(step['task_id']); result=None; rows=None; criteria=task['acceptance']
    if not error and not stopped:
        try:
            result=result_contract(output,required=True)
            if result['status']!='succeeded': error=result['summary']
            elif step['role']=='Plan' or (step['role']=='Deliver' and '<acc_plan>' in output):
                rows=plan_steps(output,json.loads(task['agent_pool']))
                if step['role']=='Deliver' and task['plan_rounds']>=3:raise ValueError('Three follow-up planning rounds exhausted.')
                if any(r['access']=='workspace-write' for r in rows) and task['execution_mode']!='workspace-write':raise ValueError('Plan exceeds task write permission.')
                if not criteria:
                    match=re.search(r'<acceptance_criteria>(.*?)</acceptance_criteria>',output,re.S)
                    criteria=match.group(1).strip() if match else ''
                    if not 1<=len(criteria)<=2000: raise ValueError('Planner must provide checkable acceptance criteria.')
            elif step['role']=='Deliver' and result.get('accepted') is not True:
                raise ValueError('Delivery requires explicit accepted:true and supporting evidence.')
        except (ValueError,TypeError) as exc: error=str(exc)
    try:
        store.workspaces.checkpoint(step)
        if not error and not stopped and step['role']=='Deliver' and not rows: store.workspaces.verify_acceptance(task)
    except Exception as exc: error=str(exc); result=None
    status='Queued'; step_status='Succeeded'
    if stopped:
        status='Paused' if stopped=='pause' else 'Cancelled'
        step_status='Pending' if stopped=='pause' else 'Cancelled'
    elif error:
        status='Blocked' if result and result['status']=='blocked' else 'Failed'; step_status=status
    elif step['role']=='Deliver': status='Completed'
    if rows and not error and not stopped:
        pool=json.loads(task['agent_pool'])
        ids={r['id']:uid() for r in rows}
        offset=step['position']
        if step['role']=='Deliver':
            store.db.execute("UPDATE steps SET role='Coordinate' WHERE id=?",(step['id'],))
            store.db.execute('UPDATE tasks SET plan_rounds=plan_rounds+1 WHERE id=?',(task['id'],))
        for i,row in enumerate(rows,1):
            config=pool[row['slot']];ident=ids[row['id']]
            deps=[ids[x] for x in row['depends_on']] or [step['id']]
            store.db.execute('INSERT INTO steps(id,task_id,position,role,agent,host,status,model,effort,instruction,node_key,dependencies,access,browser_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident,task['id'],offset+i,row['role'],config['agent'],step['host'],'Pending',config['model'],config['effort'],clean(row['instruction'],4000),row['id'],json.dumps(deps),row['access'],row['browser']))
            if len(rows)==1 and all(config[k]==step.get(k,'') for k in ('agent','model','effort')):
                store.db.execute('UPDATE steps SET swarm_call=? WHERE id=?',(step.get('swarm_call',''),ident))
        store.db.execute('UPDATE tasks SET acceptance=? WHERE id=?',(clean(criteria,2000),task['id']))
        store.event(task['id'],'plan.assigned',json.dumps(rows,ensure_ascii=False),step)
    if status=='Blocked' and result and result.get('reason')=='login_required':
        from login_handoff import login_origin
        origin=login_origin(result.get('login_url',''))
        store.db.execute("UPDATE tasks SET login_url=?,login_state='waiting',login_error='',login_step=? WHERE id=?",(origin,step['id'],task['id']))
        status='Waiting for Login'
    content=clean(output,24000)
    if content.strip() and not stopped:
        store.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',
            (uid(),task['id'],step['id'],str(step['position'])+'-'+step['role'].lower()+'-handoff.md',digest(content),len(content.encode()),now(),content))
    store.db.execute('UPDATE steps SET status=?,output=?,error=?,lease=NULL WHERE id=?',(step_status,content,clean(error or '',2000),step['id']))
    from task_graph import ancestors, settle
    if result and result['status']=='failed' and step['role'] in ('Review','Deliver') and not stopped and task['review_rounds']<3:
        steps=[dict(r) for r in store.db.execute('SELECT * FROM steps WHERE task_id=? ORDER BY position',(task['id'],))]
        upstream=ancestors(step,steps)
        eligible=[s for s in steps if s['id'] in upstream and s['role']=='Execute']
        requested=result.get('rework_ids')
        targets=[s['id'] for s in eligible if isinstance(requested,list) and s['node_key'] in requested]
        if not targets:targets=[s['id'] for s in eligible] or [step['id']]
        store.db.execute('UPDATE tasks SET pending_rework=? WHERE id=?',(json.dumps(targets),task['id']))
        store.event(task['id'],'review.rework',result['summary'],step,'Queued')
    status=settle(store,task['id'])
    if status=='Completed': store.event(task['id'],'verification.accepted','Task owner accepted the evidence.',step,status)
    store.db.execute('UPDATE tasks SET status=?,revision=revision+1 WHERE id=?',(status,task['id']))
    store.event(task['id'],'step.finished',clean(result['summary'] if result else error or status,160),step,status)
    return {'status':status}
