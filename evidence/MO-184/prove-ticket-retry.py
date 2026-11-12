import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path.cwd()
with tempfile.TemporaryDirectory(prefix='mo184-2c-') as tmp:
    base = Path(tmp)
    bin_dir = base / 'bin'
    bin_dir.mkdir()
    queue = base / 'queue'
    queue.mkdir()
    home = base / 'home'
    home.mkdir()
    env = {**os.environ, 'HOME': str(home), 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
           'EMPQ_DIR': str(queue), 'TICKET_CACHE': str(base / 'cache'),
           'TICKET_T3MCP': str(bin_dir / 't3mcp'), 'EMPQ_T3MCP': str(bin_dir / 't3mcp'),
           'TICKET_EMPQ': str(root / 'empryo/bin/empq'), 'PROOF_DIR': str(base)}
    stub = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ['PROOF_DIR'])
a = sys.argv[1:]
def read(name): return json.loads((p / name).read_text())
def write(name, data): (p / name).write_text(json.dumps(data))
if Path(sys.argv[0]).name == 'gh':
    if a[:2] == ['issue', 'view']: print(json.dumps(read('issue.json')))
    elif a[:2] == ['api', 'user']: print('proof-user')
    elif a[:2] == ['repo', 'view']: print('main')
    elif a[:2] == ['issue', 'comment']:
        issue = read('issue.json')
        issue['comments'].append({'id': str(len(issue['comments']) + 1), 'author': {'login': 'proof-user'}, 'body': a[a.index('--body') + 1]})
        write('issue.json', issue)
    elif a[:2] != ['issue', 'edit']: raise SystemExit('unexpected gh call: ' + repr(a))
elif Path(sys.argv[0]).name == 'fail-empq':
    raise SystemExit('injected empq start failure')
else:
    assert a[0] == 'call' and a[2] == '-', a
    args = json.load(sys.stdin)
    with (p / 'calls.jsonl').open('a') as f: f.write(json.dumps([a[1], args]) + '\\n')
    if a[1] == 't3_thread_list': print(json.dumps({'total': int((p / 'launched').exists())}))
    elif a[1] == 't3_thread_launch':
        (p / 'launched').touch()
        print(json.dumps({'structuredContent': {'thread': {'threadId': 'proof-finished'}}}))
    elif a[1] == 't3_thread_read':
        assert args['threadId'] == 'proof-finished', args
        print(json.dumps({'thread': {'threadId': 'proof-finished', 'status': read('status.json')}}))
    else: raise SystemExit('unexpected t3 call: ' + repr(a))
'''
    for name in ('gh', 't3mcp', 'fail-empq'):
        (bin_dir / name).write_text(stub)
        (bin_dir / name).chmod(0o700)
    def write(path, value):
        path.write_text(json.dumps(value))
    def run(*args, code=0, overrides=None):
        r = subprocess.run(args, env={**env, **(overrides or {})}, text=True, capture_output=True, timeout=15)
        assert r.returncode == code, (args, r.returncode, r.stdout, r.stderr)
        return r.stdout + r.stderr
    ticket = str(root / 'empryo/bin/ticket')
    empq = str(root / 'empryo/bin/empq')
    ref = 'shyamsivakumar/mac-ops#999'
    request = 'ticket:' + ref + ':a1'
    cfg = json.loads((root / 'empryo/config/tickets.json').read_text())
    def reset(receipt=False, intent=True):
        ledger = [{'kind': 'intent', 'attempt': 1, 'requestId': request}] if intent else []
        if receipt:
            ledger.append({'kind': 'receipt', 'attempt': 1, 'requestId': request, 'empq': 'queued #1'})
        issue = {'id': 'proof-issue', 'number': 999, 'title': 'MO-999 Retry proof', 'state': 'OPEN',
                 'url': 'https://github.com/shyamsivakumar/mac-ops/issues/999',
                 'body': '\n'.join('## ' + section + '\nFixture content.' for section in cfg['template']),
                 'labels': [{'name': 'stage:todo'}, {'name': 'type:standard'}],
                 'comments': [{'id': str(i), 'author': {'login': 'proof-user'},
                               'body': '<!-- empryo-ticket ' + json.dumps(e) + ' -->'} for i, e in enumerate(ledger)],
                 'blockedBy': {'totalCount': 0, 'nodes': []}}
        write(base / 'issue.json', issue)
        write(queue / 'queue.json', {'next': 2, 'items': []})
        write(queue / 'config.json', {'cap': 0})
        write(queue / 'dispatch-receipts.json', {})
        write(base / 'status.json', 'completed')
        (base / 'launched').unlink(missing_ok=True)
    def item(tool='t3_thread_launch'):
        return {'id': 1, 'tool': tool, 'args': {'clientRequestId': request, 'message': 'fixture',
                'modelSelection': cfg['models']['minimax']['selection']}, 'title': 'MO-999 Retry proof', 'priority': 0}
    def enqueue(tool='t3_thread_launch'):
        write(queue / 'queue.json', {'next': 2, 'items': [item(tool)]})
    def show(): return json.loads(run(ticket, 'show', ref))
    def retry(label):
        s = show()
        assert s['queued'] == [] and s['latestAttempt']['status'] == 'not running (no thread recorded)', s
        assert 'queued #' in run(ticket, 'start', ref)
        comments = json.loads((base / 'issue.json').read_text())['comments']
        assert any('"attempt":2' in c['body'] for c in comments), comments
        assert len(json.loads((queue / 'queue.json').read_text())['items']) == 1
        print('PASS ' + label + ': show not running; start enqueued attempt 2')
    reset(intent=False)
    result = run(ticket, 'start', ref, code=1, overrides={'TICKET_EMPQ': str(bin_dir / 'fail-empq')})
    assert 'empq start failed' in result
    retry('failed empq start')
    reset()
    retry('Empryo-era intent without dispatch receipt')
    reset(receipt=True)
    enqueue()
    assert 'dropped #1' in run(empq, 'drop', '1')
    retry('empq drop')
    reset(receipt=True)
    enqueue('emp_thread_launch')
    run(empq, 'dispatch')
    assert 'REFUSED #1' in (queue / 'dispatch.log').read_text()
    retry('drain REFUSED')
    reset(receipt=True)
    enqueue()
    assert show()['latestAttempt']['status'] == 'queued'
    assert 'already started: queued as empq #1' in run(ticket, 'start', ref, code=2)
    print('PASS queued item: show queued; start refused')
    reset(receipt=True)
    enqueue()
    write(queue / 'config.json', {'cap': 1})
    run(empq, 'dispatch')
    assert json.loads((queue / 'dispatch-receipts.json').read_text()) == {request: 'proof-finished'}
    assert json.loads((queue / 'queue.json').read_text())['items'] == []
    s = show()['latestAttempt']
    assert s == {'attempt': 1, 'threadId': 'proof-finished', 'status': 'completed'}, s
    assert 'checks passed' in run(ticket, 'start', ref, '--dry-run')
    print('PASS drained finished thread: receipt persisted before removal; show completed; retry allowed')
    write(base / 'status.json', 'running')
    assert 'thread proof-finished is running' in run(ticket, 'start', ref, code=2)
    print('PASS recorded live thread: start refused')
    calls = [json.loads(line)[0] for line in (base / 'calls.jsonl').read_text().splitlines()]
    assert set(calls) <= {'t3_thread_list', 't3_thread_launch', 't3_thread_read'}, calls
    print('PASS all gh/t3mcp calls stubbed; temporary queue, cache and HOME only; no emp or gate called')
