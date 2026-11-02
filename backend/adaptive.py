"""Task-specific staffing, with explicit scope and evidence-based delivery."""
import json
import re

def prompt(step):
    task=step['task']
    if step['role']=='Plan':
        return ('Choose the smallest useful team for this task from the numbered available configurations below. '
            'You may reuse a configuration for multiple assignments; independent review is optional when warranted. '
            'Assignments run in the listed order on this host. Do not assume parallel execution. '
            'For a simple task use one Deliver assignment that does the work and checks its own result. '
            'For a larger task use Execute assignments, optional Review assignments, then exactly one final Deliver. '
            'Return <acc_plan>{"steps":[{"role":"Execute|Review|Deliver","slot":0,"instruction":"specific responsibility and evidence required"}]}</acc_plan> '
            'with 1–24 assignments. The last assignment must be Deliver. Only Codex Execute or Deliver can edit files, '
            'and only when this task has workspace-write permission. Generate <acceptance_criteria>checkable criteria</acceptance_criteria> '
            'if none were provided. Finish with a succeeded acc_result when the plan is ready. Available configurations: '+task['agent_pool'])
    return ('Your assignment: '+step.get('instruction','')+'. Execute only this assignment; previous results are supplied below. '
            'For Review use failed with concrete feedback when changes are required. '
            'For Deliver, complete any assigned work, integrate previous findings and verify the task acceptance criteria. '
            'Only Deliver may declare the whole task complete. A succeeded Deliver acc_result MUST include "accepted":true '
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
    return rows

def finish(store, step, output, error, stopped):
    from core import clean, digest, now, uid, result_contract
    task=store.get_task(step['task_id']); result=None; rows=None; criteria=task['acceptance']
    if not error and not stopped:
        try:
            result=result_contract(output,required=True)
            if result['status']!='succeeded': error=result['summary']
            elif step['role']=='Plan':
                rows=plan_steps(output,json.loads(task['agent_pool']))
                if not criteria:
                    match=re.search(r'<acceptance_criteria>(.*?)</acceptance_criteria>',output,re.S)
                    criteria=match.group(1).strip() if match else ''
                    if not 1<=len(criteria)<=2000: raise ValueError('Planner must provide checkable acceptance criteria.')
            elif step['role']=='Deliver' and result.get('accepted') is not True:
                raise ValueError('Delivery requires explicit accepted:true and supporting evidence.')
        except (ValueError,TypeError) as exc: error=str(exc)
    try:
        store.workspaces.checkpoint(step)
        if not error and not stopped and step['role']=='Deliver': store.workspaces.verify_acceptance(task)
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
        for i,row in enumerate(rows,1):
            config=pool[row['slot']]
            ident=uid()
            store.db.execute('INSERT INTO steps(id,task_id,position,role,agent,host,status,model,effort,instruction) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (ident,task['id'],i,row['role'],config['agent'],step['host'],'Pending',config['model'],config['effort'],clean(row['instruction'],4000)))
            if len(rows)==1 and all(config[k]==step.get(k,'') for k in ('agent','model','effort')):
                store.db.execute('UPDATE steps SET swarm_call=? WHERE id=?',(step.get('swarm_call',''),ident))
        store.db.execute('UPDATE tasks SET acceptance=? WHERE id=?',(clean(criteria,2000),task['id']))
        store.event(task['id'],'plan.assigned',json.dumps(rows,ensure_ascii=False),step)
    if status=='Blocked' and result and result.get('reason')=='login_required':
        from login_handoff import login_origin
        origin=login_origin(result.get('login_url',''))
        store.db.execute("UPDATE tasks SET login_url=?,login_state='waiting',login_error='' WHERE id=?",(origin,task['id']))
        status='Waiting for Login'
    content=clean(output,24000)
    if content.strip() and not stopped:
        store.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',
            (uid(),task['id'],step['id'],str(step['position'])+'-'+step['role'].lower()+'-handoff.md',digest(content),len(content.encode()),now(),content))
    store.db.execute('UPDATE steps SET status=?,output=?,error=?,lease=NULL WHERE id=?',(step_status,content,clean(error or '',2000),step['id']))
    if result and result['status']=='failed' and step['role'] in ('Review','Deliver') and not stopped and task['review_rounds']<3:
        previous=store.db.execute("SELECT position FROM steps WHERE task_id=? AND role='Execute' AND position<? ORDER BY position DESC LIMIT 1",(task['id'],step['position'])).fetchone()
        # A single-agent delivery revises itself; a team returns to the preceding executor.
        target=previous['position'] if previous else step['position']
        store.db.execute("UPDATE steps SET status='Pending',attempt=NULL,lease=NULL,error=NULL WHERE task_id=? AND position>=?",(task['id'],target))
        store.db.execute('UPDATE tasks SET review_rounds=review_rounds+1 WHERE id=?',(task['id'],))
        store.event(task['id'],'review.rework',result['summary'],step,'Queued');status='Queued'
    if status=='Completed': store.event(task['id'],'verification.accepted','Task owner accepted the evidence.',step,status)
    store.db.execute('UPDATE tasks SET status=?,revision=revision+1 WHERE id=?',(status,task['id']))
    store.event(task['id'],'step.finished',clean(result['summary'] if result else error or status,160),step,status)
    return {'status':status}
