"""Validated task-bound CLI selections, separate from native CLI configuration."""
import re

EFFORTS = {'', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}
DEFAULTS = {'roles':['codex','codex','codex'], 'codex':{'model':'','effort':''}, 'claude':{'model':'','effort':''}}

def selection(agent, data):
    if not isinstance(data,dict) or set(data)-{'model','effort'}: raise ValueError('Invalid model settings')
    model=data.get('model',''); effort=data.get('effort','')
    if not isinstance(model,str) or (model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,159}',model)):
        raise ValueError('Use an exact model ID without spaces or shell characters')
    if not isinstance(effort,str) or effort not in EFFORTS: raise ValueError('Invalid reasoning effort')
    if agent=='claude' and effort not in ('','low','medium','high','xhigh','max'): raise ValueError('Claude supports low, medium, high, xhigh or max; availability depends on the model')
    if agent.startswith('api:') and (model or effort): raise ValueError('API models use their provider profile; CLI effort is not supported')
    return {'model':model,'effort':effort}

def defaults(data):
    if not isinstance(data,dict) or set(data)!={'roles','codex','claude'}: raise ValueError('Invalid agent defaults')
    roles=data['roles']
    if not isinstance(roles,list) or len(roles)!=3 or any(a not in ('codex','claude') for a in roles):
        raise ValueError('Default roles must select Codex or Claude Code')
    return {'roles':roles,**{a:selection(a,data[a]) for a in ('codex','claude')}}

def validate_catalog(agent,value,models):
    selected=selection(agent,value)
    if not selected['model']:
        if selected['effort']:raise ValueError('Choose a model before overriding reasoning effort')
        return
    model=next((m for m in models if m['id']==selected['model']),None)
    if not model:raise ValueError(f"Model {selected['model']} is not in the current {agent} model list. Refresh and select a listed model.")
    if selected['effort'] and selected['effort'] not in model.get('efforts',[]):
        raise ValueError(f"Reasoning effort {selected['effort']} is not supported by {selected['model']}")
