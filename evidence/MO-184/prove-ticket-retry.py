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
    elif a[:2] == ['issue', 'close']: (p / 'closed').touch()
    elif a[:2] != ['issue', 'edit']: raise SystemExit('unexpected gh call: ' + repr(a))
elif Path(sys.argv[0]).name == 'fail-empq':
    raise SystemExit('injected empq start failure')
else:
    assert a[0] == 'call' and a[2] == '-', a
    args = json.load(sys.stdin)
    with (p / 'calls.jsonl').open('a') as f: f.write(json.dumps([a[1], args]) + '\\n')
    if a[1] == 't3_thread_list': print(json.dumps({'total': int((p / 'launched').exists() and not (p / 'launch-mode').exists())}))
    elif a[1] == 't3_thread_launch':
        (p / 'launched').touch()
        mode = (p / 'launch-mode').read_text() if (p / 'launch-mode').exists() else 'nested'
        if mode == 'invalid': print('not json')
        elif mode == 'missing': print('{}')
        elif mode == 'direct': print(json.dumps({'threadId': 'proof-finished'}))
        else: print(json.dumps({'thread': {'threadId': 'proof-finished'}}))
    elif a[1] == 't3_thread_read':
        mode = read('status.json')
        if mode in ('thread_not_found', 'offline'):
            print(json.dumps([{'type': 'text', 'text': json.dumps({'code': mode})}]), file=sys.stderr)
            raise SystemExit(1)
        if mode == 'mismatch': args['threadId'] = 'unrelated-review'
        status = 'running' if args['threadId'] == 'older-attempt' else mode
        print(json.dumps({'thread': {'threadId': args['threadId'], 'status': status}}))
    elif a[1] == 't3_thread_interrupt':
        assert args == {'threadId': 'older-attempt', 'stop': True}, args
        print('{}')
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
        for name in ('launched', 'closed', 'launch-mode'):
            (base / name).unlink(missing_ok=True)
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
    reset()
    write(queue / 'dispatch-receipts.json', {request: 'deleted-attempt'})
    write(base / 'status.json', 'thread_not_found')
    assert show()['latestAttempt']['status'] == 'not running (thread not found)'
    assert 'queued #' in run(ticket, 'start', ref)
    reset()
    write(queue / 'dispatch-receipts.json', {request: 'deleted-attempt'})
    write(base / 'status.json', 'thread_not_found')
    assert 'no live thread' in run(ticket, 'abandon', ref, '--reason', 'fixture')
    assert (base / 'closed').exists()
    print('PASS deleted thread: show not running; start retries; abandon closes')
    for status in ('offline', 'mismatch'):
        reset()
        write(queue / 'dispatch-receipts.json', {request: 'proof-finished'})
        write(base / 'status.json', status)
        for command in (('show', ref), ('start', ref), ('abandon', ref, '--reason', 'fixture')):
            assert 'refused:' in run(ticket, *command, code=2)
        assert not (base / 'closed').exists()
    print('PASS other transport failures and identity mismatch refuse without closing')
    reset()
    issue = json.loads((base / 'issue.json').read_text())
    issue['comments'].append({'id': '2', 'author': {'login': 'proof-user'},
                              'body': '<!-- empryo-ticket ' + json.dumps({'kind': 'intent', 'attempt': 2}) + ' -->'})
    write(base / 'issue.json', issue)
    write(queue / 'dispatch-receipts.json', {request: 'older-attempt', request[:-1] + '2': 'proof-finished'})
    assert 'older-attempt is running' in run(ticket, 'start', ref, code=2)
    assert 'interrupted thread older-attempt' in run(ticket, 'abandon', ref, '--reason', 'fixture')
    print('PASS abandon interrupts older live attempt only; completed latest attempt is untouched')
    for mode in ('missing', 'invalid'):
        reset()
        enqueue()
        q = json.loads((queue / 'queue.json').read_text())
        second = item()
        second.update(id=2, args={'message': 'fixture', 'modelSelection': cfg['models']['minimax']['selection']})
        q['items'].append(second)
        write(queue / 'config.json', {'cap': 1})
        (base / 'launch-mode').write_text(mode)
        write(queue / 'queue.json', q)
        before = (base / 'calls.jsonl').read_text().splitlines()
        run(empq, 'dispatch')
        run(empq, 'dispatch')
        after = (base / 'calls.jsonl').read_text().splitlines()[len(before):]
        launches = [json.loads(line) for line in after if json.loads(line)[0] == 't3_thread_launch']
        assert len(launches) == 2, launches
        remaining = json.loads((queue / 'queue.json').read_text())['items']
        assert len(remaining) == 1 and remaining[0]['id'] == 1 and remaining[0]['attempts'] == 3, remaining
        assert json.loads((queue / 'dispatch-receipts.json').read_text()) == {}
        assert 'started #2' in (queue / 'dispatch.log').read_text()
        assert 'queued' == show()['latestAttempt']['status']
        assert 'already started' in run(ticket, 'start', ref, code=2)
    print('PASS missing ID and invalid JSON: held at retry limit without relaunch; next item dispatched; uncertain attempt stays blocked')
    reset()
    enqueue()
    write(queue / 'config.json', {'cap': 1})
    (base / 'launch-mode').write_text('direct')
    run(empq, 'dispatch')
    assert show()['latestAttempt']['threadId'] == 'proof-finished'
    print('PASS direct thread ID reply persists receipt')
    reset(intent=False)
    issue = json.loads((base / 'issue.json').read_text())
    issue['labels'] = [{'name': 'stage:todo'}]
    write(base / 'issue.json', issue)
    assert 'missing type label' in run(ticket, 'start', ref, code=2)
    print('PASS original missing type requirement preserved once in start validation')
    calls = [json.loads(line)[0] for line in (base / 'calls.jsonl').read_text().splitlines()]
    assert set(calls) <= {'t3_thread_list', 't3_thread_launch', 't3_thread_read', 't3_thread_interrupt'}, calls
    print('PASS all gh/t3mcp calls stubbed; temporary queue, cache and HOME only; no emp or gate called')
