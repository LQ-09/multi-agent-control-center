"""Pause existing ACC tasks via the normal SSH authority protocol; never launch agents."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from bridge import Remote, DEFAULT


def pause_all(remote):
    snapshot = remote.call('snapshot')
    paused = 0
    for task in snapshot['tasks']:
        if task['status'] in ('Completed', 'Cancelled', 'Paused'):
            continue
        remote.call('control', {'id': task['id'], 'action': 'pause', 'revision': task['revision']})
        paused += 1
    final = remote.call('snapshot')
    pending = [t['title'] for t in final['tasks'] if t['status'] not in ('Paused', 'Completed', 'Cancelled')]
    if pending:
        raise RuntimeError('Pause requested, but some tasks have not stopped: ' + ', '.join(pending))
    if any(s.get('status') == 'Running' or s.get('lease') is not None for s in final['steps']):
        raise RuntimeError('Execution outcome still needs reconciliation; do not update yet.')
    print(f'Paused {paused} tasks. Existing history and artifacts retained. Refresh ACC, then install the update.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('alias', nargs='?', default='win-server')
    parser.add_argument('--root', default='C:/Users/Administrator/AgentControlCenter/state')
    parser.add_argument('--service', default='C:/Users/Administrator/AgentControlCenter/backend/service.py')
    args = parser.parse_args()
    config = {**DEFAULT, 'ssh_alias': args.alias, 'windows_python': 'python',
              'windows_service': args.service, 'windows_root': args.root,
              'remote_os': 'windows', 'profile': 'split'}
    remote = Remote(config)
    try:
        remote.call('hello')
        pause_all(remote)
    finally:
        remote.close()

if __name__ == '__main__':
    main()
