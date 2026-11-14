#!/usr/bin/env python3
"""Offline oracle and synthetic evidence reporting. Never execute untrusted model output."""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import random
from pathlib import Path
import sys
import tempfile

try:
    from . import vibe_host
except ImportError:
    import vibe_host

Z = 1.959963984540054


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_bytes().decode('utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f'invalid UTF-8 JSON: {path}: {exc}') from exc


def reject_links(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'symlink path rejected: {part}')


def check_output(source, out):
    source, out = Path(source), Path(out)
    if '..' in source.parts or '..' in out.parts:
        raise ValueError('parent traversal in path is not allowed')
    source, out = source.absolute(), out.absolute()
    reject_links(source)
    reject_links(out)
    if out.exists():
        raise ValueError(f'output already exists: {out}')
    if source == out or source in out.parents or out in source.parents:
        raise ValueError('input and output overlap')


def asset(root, relative):
    if not isinstance(relative, str):
        raise ValueError('asset path must be a string')
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('unsafe asset path')
    path = root / rel
    reject_links(path)
    if not path.exists():
        raise ValueError(f'missing asset: {relative}')
    return path


def wilson(success, total):
    if total <= 0 or success < 0 or success > total:
        raise ValueError('invalid counts')
    p = success / total
    den = 1 + Z * Z / total
    center = (p + Z * Z / (2 * total)) / den
    radius = Z * math.sqrt(p * (1 - p) / total + Z * Z / (4 * total * total)) / den
    return center - radius, center + radius


def newcombe(ts, tn, cs, cn):
    pt, pc = ts / tn, cs / cn
    lt, ut = wilson(ts, tn)
    lc, uc = wilson(cs, cn)
    delta = pt - pc
    return delta - math.sqrt((pt - lt) ** 2 + (uc - pc) ** 2), delta + math.sqrt((ut - pt) ** 2 + (pc - lc) ** 2)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def tree_snapshot(root):
    snapshot = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            snapshot[relative] = {'type': 'symlink', 'target': os.readlink(path)}
        elif path.is_file():
            snapshot[relative] = {'type': 'file', 'sha256': digest(path), 'mode': path.stat().st_mode & 0o777}
        elif path.is_dir():
            snapshot[relative] = {'type': 'directory', 'mode': path.stat().st_mode & 0o777}
        else:
            snapshot[relative] = {'type': 'other'}
    return snapshot


def oracle(battery_path, out):
    check_output(battery_path.parent, out)
    data = read_json(battery_path)
    if not isinstance(data, dict) or not isinstance(data.get('tasks'), list):
        raise ValueError('invalid battery')
    root = battery_path.parent
    declared = set(data['assets'])
    present = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'symlink in battery: {path}')
        if path.is_file() and path.name not in ('battery.json', 'provenance.json'):
            present.add(str(path.relative_to(root)))
    if declared != present:
        raise ValueError('battery asset set mismatch')
    for name, expected in data['assets'].items():
        path = asset(root, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'asset hash mismatch: {name}')
    cases = []
    for task in data['tasks']:
        checker = asset(root, task['checker'])
        spec = importlib.util.spec_from_file_location('checker_' + task['id'], checker)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        public = asset(root, task['public'])
        for case in task['cases']:
            before = tree_snapshot(public)
            try:
                result = module.check(public, asset(root, case['submission']))
                dimensions = result['dimensions']
                dimensions['input_integrity'] = tree_snapshot(public) == before
                passed = all(value is True for value in dimensions.values())
                expected = case.get('fails')
                matched = passed if expected is None else dimensions.get(expected) is False and dimensions['input_integrity']
                cases.append({'task': task['id'], 'case': case['name'], 'expected_failure': expected, 'matched': matched, **result})
            except Exception as exc:
                cases.append({'task': task['id'], 'case': case['name'], 'expected_failure': case.get('fails'), 'matched': False, 'error': f'{type(exc).__name__}: {exc}'})
    result = {'kind': 'offline trusted reference and negative cases', 'model_runs': 0, 'battery_sha256': digest(battery_path), 'passed': bool(cases) and all(c['matched'] for c in cases), 'cases': cases}
    out.mkdir(parents=True)
    write_json(out / 'oracle.json', result)
    return 0 if result['passed'] else 1


def collect(source, out):
    check_output(source, out)
    data = read_json(source)
    if not isinstance(data, dict) or data.get('kind') != 'synthetic' or not isinstance(data.get('trials'), list):
        raise ValueError('only synthetic results may be collected')
    out.mkdir(parents=True)
    (out / 'results.json').write_bytes(source.read_bytes())
    write_json(out / 'collection.json', {'kind': 'synthetic', 'source': str(source), 'sha256': digest(source), 'model_runs': 0, 'live_verified': False})
    return 0


def report(source, out, strict):
    check_output(source, out)
    data = read_json(source)
    if not isinstance(data, dict) or data.get('kind') != 'synthetic' or not isinstance(data.get('trials'), list):
        raise ValueError('only explicitly synthetic trial input is supported')
    trials = data['trials']
    ids = set()
    for trial in trials:
        if not isinstance(trial, dict) or not all(isinstance(trial.get(key), str) and trial[key] for key in ('id', 'task', 'arm', 'status')):
            raise ValueError('invalid trial')
        if trial['id'] in ids or trial['arm'] not in ('control', 'treatment') or trial['status'] not in ('pass', 'fail', 'timeout', 'skipped', 'missing', 'facility_failure'):
            raise ValueError('invalid or duplicate trial')
        ids.add(trial['id'])
    slots = data.get('expected_slots')
    if not isinstance(slots, list) or not slots:
        raise ValueError('expected_slots required')
    slot_map = {}
    for slot in slots:
        if not isinstance(slot, dict) or not all(isinstance(slot.get(k), str) and slot[k] for k in ('id', 'task', 'arm')) or slot['arm'] not in ('control', 'treatment') or slot['id'] in slot_map:
            raise ValueError('invalid expected slot')
        slot_map[slot['id']] = slot
    for trial in trials:
        slot = slot_map.get(trial['id'])
        if slot is None or any(trial[k] != slot[k] for k in ('task', 'arm')):
            raise ValueError('trial does not match an expected slot')
    summaries = []
    complete = True
    batch_integrity_violation = any(trial.get('integrity') == 'violation' for trial in trials)
    for task in sorted(set(slot['task'] for slot in slots)):
        groups = {}
        for arm in ('control', 'treatment'):
            rows = [t for t in trials if t['task'] == task and t['arm'] == arm]
            quality = [
                trial for trial in rows
                if trial['status'] in ('pass', 'fail', 'timeout')
                and trial.get('started') is True
                and trial.get('integrity') == 'ok'
                and (trial['status'] == 'timeout' or trial.get('required_checks') == 'complete')
            ]
            passed = sum(t['status'] == 'pass' for t in quality)
            gaps = [t for t in rows if t not in quality or t.get('judge') != 'complete']
            expected = [slot for slot in slots if slot['task'] == task and slot['arm'] == arm]
            gaps += [{'id': slot['id'], 'status': 'missing'} for slot in expected if slot['id'] not in ids]
            if gaps:
                complete = False
            groups[arm] = {
                'planned': len(expected),
                'started': sum(bool(trial.get('started')) for trial in rows),
                'completed': sum(trial['status'] in ('pass', 'fail') for trial in rows),
                'quality_denominator': len(quality),
                'pass': passed,
                'wilson95': wilson(passed, len(quality)) if quality else None,
                'gaps': gaps,
            }
        t, c = groups['treatment'], groups['control']
        difference = None
        severe = batch_integrity_violation
        if t['quality_denominator'] and c['quality_denominator'] and not severe:
            interval = newcombe(t['pass'], t['quality_denominator'], c['pass'], c['quality_denominator'])
            interpretation = (
                '区间含 0，未观察到显著差异'
                if interval[0] <= 0 <= interval[1]
                else '区间不含 0；仍需审查实验有效性'
            )
            difference = {
                'estimate': t['pass'] / t['quality_denominator'] - c['pass'] / c['quality_denominator'],
                'newcombe95': interval,
                'interpretation': interpretation,
            }
        summaries.append({
            'task': task,
            'arms': groups,
            'difference': difference,
            'integrity_violations': sum(
                row.get('integrity') == 'violation' for row in trials if row['task'] == task
            ),
            'comparison_stopped': severe,
        })
    if not trials:
        complete = False
    output = {'kind': 'synthetic; not model evidence', 'model_runs': 0, 'live_verified': False, 'live_complete': False, 'missing_live_evidence': ['oracle binding', 'native routing', 'execution isolation', 'independent judge'], 'source': str(source), 'source_sha256': digest(source), 'complete': complete, 'limitations': '小样本；假设各上下文近似独立、组内条件稳定；缓存与时间变化可能影响结果。隔离、授权和路由未认证。', 'results': summaries, 'raw_trials': trials}
    out.mkdir(parents=True)
    write_json(out / 'report.json', output)
    (out / 'report.md').write_text('# 合成离线报告（真实模型 run = 0）\n\n' + output['limitations'] + '\n\n```json\n' + json.dumps(summaries, ensure_ascii=False, indent=2) + '\n```\n', encoding='utf-8')
    return 1 if strict else 0



SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
STATISTICS = {'method': 'wilson-newcombe-independent', 'z': Z}


def safe_id(value):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError('unsafe identifier')
    return value


def input_path(value, base):
    if not isinstance(value, str) or not value:
        raise ValueError('path must be a nonempty string')
    path = Path(value)
    if '..' in path.parts:
        raise ValueError('parent traversal in path is not allowed')
    path = path if path.is_absolute() else base / path
    reject_links(path)
    if not path.exists():
        raise ValueError(f'missing input: {path}')
    return path.absolute()


def ensure_output(out, sources):
    for source in sources:
        check_output(source, out)


def checked_tree(path):
    reject_links(path)
    if not path.is_dir():
        raise ValueError(f'expected directory: {path}')
    snapshot = tree_snapshot(path)
    if any(item['type'] not in ('file', 'directory') for item in snapshot.values()):
        raise ValueError('non-regular file or symlink in input tree')
    return snapshot


def snapshot_hash(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate_battery(battery_path):
    data = read_json(battery_path)
    if not isinstance(data, dict) or not isinstance(data.get('assets'), dict) or not isinstance(data.get('tasks'), list):
        raise ValueError('invalid battery')
    root = battery_path.parent
    tree = checked_tree(root)
    present = {name for name, item in tree.items() if item['type'] == 'file' and name not in ('battery.json', 'provenance.json')}
    if present != set(data['assets']):
        raise ValueError('battery asset set mismatch')
    for name, expected in data['assets'].items():
        if digest(asset(root, name)) != expected:
            raise ValueError(f'battery asset hash mismatch: {name}')
    tasks = []
    names = set()
    for item in data['tasks']:
        name = safe_id(item['id'])
        if name in names:
            raise ValueError('duplicate task ID')
        names.add(name)
        public_rel = Path(item['public'])
        if 'private' in public_rel.parts:
            raise ValueError('private path used as public input')
        public = asset(root, item['public'])
        public_tree = checked_tree(public)
        forbidden = {'private', 'reference', 'negative', '.git', 'checker.py'}
        if any(forbidden.intersection(Path(name).parts) for name in public_tree):
            raise ValueError('public fixture contains private or repository assets')
        if not (public / 'prompt.md').is_file():
            raise ValueError('public prompt missing')
        checker_path = asset(root, item['checker'])
        if checker_path == public or public in checker_path.parents:
            raise ValueError('checker must be outside public tree')
        tasks.append({'id': name, 'public': str(public), 'public_tree': public_tree,
                      'fixture_sha256': snapshot_hash(public_tree),
                      'prompt_sha256': digest(public / 'prompt.md'),
                      'checker': str(checker_path), 'checker_sha256': digest(checker_path)})
    if not tasks:
        raise ValueError('battery has no tasks')
    return tasks, tree



def build_trials(tasks, repetition, target, permissions, limits, required_dimensions):
    trials = []
    for task in tasks:
        conditions = {'prompt_sha256': task['prompt_sha256'], 'fixture_sha256': task['fixture_sha256'],
                      'checker_sha256': task['checker_sha256'], 'target': target,
                      'permissions': permissions, 'limits': limits,
                      'required_dimensions': required_dimensions.get(task['id'])}
        for rep in range(1, repetition + 1):
            arms = ('control', 'treatment') if rep % 2 else ('treatment', 'control')
            for arm in arms:
                trial_id = safe_id(f"{task['id']}-r{rep:02d}-{arm}")
                trials.append({'id': trial_id, 'task': task['id'], 'repetition': rep,
                               'arm': arm, 'conditions': conditions})
    return trials

def plan(config_path, out):
    config_path = input_path(str(config_path), Path.cwd())
    config_bytes = config_path.read_bytes()
    try:
        data = json.loads(config_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid config UTF-8 JSON') from exc
    config_sha = hashlib.sha256(config_bytes).hexdigest()
    if not isinstance(data, dict) or data.get('kind') not in ('synthetic', 'live'):
        raise ValueError('kind must be synthetic or live')
    battery_path = input_path(data['battery'], config_path.parent)
    tasks, battery_tree = validate_battery(battery_path)
    documents = []
    seen = set()
    if not isinstance(data.get('documents'), list):
        raise ValueError('documents must be a list')
    for entry in data['documents']:
        path = input_path(entry, config_path.parent)
        if not path.is_file() or path.name in seen:
            raise ValueError('documents must be distinct regular files with unique names')
        seen.add(path.name)
        raw_document = path.read_bytes()
        documents.append({'path': str(path), 'name': path.name,
                          'sha256': hashlib.sha256(raw_document).hexdigest(),
                          'snapshot_base64': base64.b64encode(raw_document).decode('ascii')})
    repetition = data.get('repetitions')
    budget = data.get('budget')
    if type(repetition) is not int or not 1 <= repetition <= 3 or not isinstance(budget, dict):
        raise ValueError('invalid repetitions or budget')
    count = len(tasks) * repetition * 2
    if budget.get('producer_runs') != count or budget.get('judge_runs') != 1 or budget.get('concurrency') != 1:
        raise ValueError('budget must match planned slots, one judge, concurrency 1')
    if count > 12:
        raise ValueError('producer run limit exceeded')
    target = data.get('target')
    limits = data.get('limits')
    permissions = data.get('permissions')
    valid_target = (
        isinstance(target, dict)
        and isinstance(target.get('providerInstanceId'), str)
        and bool(target['providerInstanceId'])
        and isinstance(target.get('model'), str)
        and bool(target['model'])
        and isinstance(target.get('options'), dict)
    )
    if not valid_target:
        raise ValueError('invalid target')
    valid_limits = (
        isinstance(limits, dict)
        and type(limits.get('seconds')) is int
        and 1 <= limits['seconds'] <= 900
        and type(limits.get('output_tokens')) is int
        and 1 <= limits['output_tokens'] <= 24000
    )
    if not valid_limits:
        raise ValueError('invalid limits')
    if not isinstance(permissions, list) or not all(isinstance(v, str) and v for v in permissions):
        raise ValueError('invalid permissions')
    if data.get('approval_status') not in ('approved', 'unapproved', 'revoked'):
        raise ValueError('invalid approval status')
    ensure_output(out, [config_path, battery_path.parent, *(Path(d['path']) for d in documents)])
    required_dimensions = data.get('required_dimensions', {})
    if not isinstance(required_dimensions, dict):
        raise ValueError('required_dimensions must be an object')
    task_ids = {task['id'] for task in tasks}
    if set(required_dimensions) - task_ids:
        raise ValueError('required_dimensions contains unknown task')
    for dimensions in required_dimensions.values():
        if (not isinstance(dimensions, list) or not dimensions
                or not all(isinstance(name, str) and name for name in dimensions)
                or len(dimensions) != len(set(dimensions))):
            raise ValueError('invalid required dimension list')
    trials = build_trials(tasks, repetition, target, permissions, limits, required_dimensions)
    judge_limits = data.get('judge_limits', {'seconds': 900, 'output_tokens': 16000})
    wall_seconds = data.get('wall_seconds', 12600)
    valid_judge_limits = (
        isinstance(judge_limits, dict)
        and type(judge_limits.get('seconds')) is int
        and 1 <= judge_limits['seconds'] <= 900
        and type(judge_limits.get('output_tokens')) is int
        and 1 <= judge_limits['output_tokens'] <= 16000
    )
    if not valid_judge_limits or type(wall_seconds) is not int or not 1 <= wall_seconds <= 12600:
        raise ValueError('invalid judge or wall-clock limit')
    result = {'version': 1, 'kind': data['kind'], 'synthetic_only': data['kind'] == 'synthetic',
              'model_runs': 0 if data['kind'] == 'synthetic' else None,
              'model_runs_started_by_script': 0, 'config_path': str(config_path), 'config_sha256': config_sha,
              'battery_path': str(battery_path), 'battery_sha256': digest(battery_path),
              'battery_tree_sha256': snapshot_hash(battery_tree), 'battery_tree': battery_tree,
              'tasks': tasks, 'documents': documents, 'budget': budget, 'repetitions': repetition, 'judge_limits': judge_limits, 'wall_seconds': wall_seconds, 'target': target,
              'required_dimensions': required_dimensions,
              'permissions': permissions, 'limits': limits, 'statistics': STATISTICS,
              'approval_status': data['approval_status'], 'approval_ref': data.get('approval_ref'),
              'approval_note': 'Audit reference only; no authorization or capability is authenticated.',
              'hard_limit_capability': 'unknown', 'trials': trials}
    if digest(config_path) != config_sha:
        raise ValueError('config changed while planning')
    out.mkdir(parents=True)
    write_json(out / 'plan.json', result)
    return 0


def load_plan(path):
    path = input_path(str(path), Path.cwd())
    data = read_json(path)
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('trials'), list):
        raise ValueError('invalid plan')
    if not isinstance(data.get('documents'), list):
        raise ValueError('invalid plan documents')
    names = set()
    for document in data['documents']:
        if not isinstance(document, dict) or not isinstance(document.get('path'), str):
            raise ValueError('invalid plan document')
        name = document.get('name')
        if (not isinstance(name, str) or not name or Path(name).name != name
                or name in ('.', '..') or name != Path(document['path']).name or name in names):
            raise ValueError('unsafe plan document name')
        names.add(name)
        try:
            raw = base64.b64decode(document['snapshot_base64'], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError('invalid frozen document bytes') from exc
        if hashlib.sha256(raw).hexdigest() != document.get('sha256'):
            raise ValueError('frozen document digest mismatch')
    expected = build_trials(data['tasks'], data['repetitions'], data['target'], data['permissions'],
                            data['limits'], data['required_dimensions'])
    if data['trials'] != expected or len(expected) != data['budget']['producer_runs'] or len(expected) > 12:
        raise ValueError('plan trial conditions, ordering or budget changed')
    if data['budget']['judge_runs'] != 1 or data['budget']['concurrency'] != 1:
        raise ValueError('plan judge budget or concurrency changed')
    return path, data


def get_trial(plan_data, trial_id):
    safe_id(trial_id)
    matches = [trial for trial in plan_data['trials'] if trial.get('id') == trial_id]
    if len(matches) != 1:
        raise ValueError('unknown or duplicate trial ID')
    return matches[0]


def verify_plan_inputs(plan_data):
    config = input_path(plan_data['config_path'], Path.cwd())
    if digest(config) != plan_data['config_sha256']:
        raise ValueError('frozen config changed; replan required')
    battery = input_path(plan_data['battery_path'], Path.cwd())
    if digest(battery) != plan_data['battery_sha256']:
        raise ValueError('battery manifest changed')
    tasks, tree = validate_battery(battery)
    if snapshot_hash(tree) != plan_data['battery_tree_sha256'] or tasks != plan_data['tasks']:
        raise ValueError('frozen battery inputs changed')
    for doc in plan_data['documents']:
        path = input_path(doc['path'], Path.cwd())
        if not path.is_file() or digest(path) != doc['sha256']:
            raise ValueError('frozen document changed')


def prepare(plan_path, trial_id, out, host_context=None):
    plan_path, data = load_plan(plan_path)
    trial = get_trial(data, trial_id)
    live = data.get('kind') == 'live'
    if live:
        vibe_host.allow_prepare(host_context, digest(plan_path), data, trial)
    if data.get('approval_status') != 'approved':
        raise ValueError('plan approval status is absent or revoked')
    if len(data['trials']) != data['budget']['producer_runs'] or data['budget']['judge_runs'] != 1:
        raise ValueError('budget or planned slots changed')
    verify_plan_inputs(data)
    task = next(item for item in data['tasks'] if item['id'] == trial['task'])
    sources = [plan_path, Path(data['battery_path']).parent] + [Path(d['path']) for d in data['documents']]
    ensure_output(out, sources)
    out.mkdir(parents=True)
    shutil.copytree(task['public'], out / 'public', symlinks=False)
    if trial['arm'] == 'treatment' and data['documents']:
        (out / 'documents').mkdir()
        for doc in data['documents']:
            frozen = base64.b64decode(doc['snapshot_base64'], validate=True)
            (out / 'documents' / doc['name']).write_bytes(frozen)
    payload = {'kind': 'host-handoff' if live else 'synthetic-test-only', 'launchable': live,
               'model_runs': None if live else 0, 'model_runs_started_by_script': 0,
               'trial_id': trial['id'], 'public_path': 'public', 'prompt_path': 'public/prompt.md',
               'documents_path': 'documents' if trial['arm'] == 'treatment' and data['documents'] else None,
               'target_request': data['target'], 'permissions': data['permissions'], 'limits': data['limits'],
               'instruction': ('Host must independently verify authorization and isolation before launch.' if live
                               else 'Synthetic offline copy. Do not launch a model or delegate.'),
               'limitations': ['Host callback evidence must be independently authenticated by the caller',
                               'timeoutMs is a wait, not a hard execution limit']}
    write_json(out / 'payload.json', payload)
    return 0


RESULT_STATUSES = {'pass', 'fail', 'timeout', 'skipped', 'missing', 'facility_failure'}


def collect_trial(plan_path, trial_id, receipt_path, submission, out, host_context=None):
    plan_path, data = load_plan(plan_path)
    trial = get_trial(data, trial_id)
    receipt_path = input_path(str(receipt_path), Path.cwd())
    submission = input_path(str(submission), Path.cwd())
    receipt = read_json(receipt_path)
    if not isinstance(receipt, dict):
        raise ValueError('receipt must be an object')
    if receipt.get('trial_id') is not None and receipt['trial_id'] != trial_id:
        raise ValueError('receipt trial mismatch')
    if data['kind'] == 'synthetic' and receipt.get('trial_id') != trial_id:
        raise ValueError('synthetic receipt trial mismatch')
    for field, expected in (('plan_sha256', digest(plan_path)),
                            ('checker_sha256', trial['conditions']['checker_sha256'])):
        if field in receipt and receipt[field] != expected:
            raise ValueError(f'receipt {field} mismatch')
    actual_model = receipt.get('executedModel')
    if actual_model is not None and not isinstance(actual_model, str):
        raise ValueError('executedModel must be string or null')
    tree = checked_tree(submission)
    native = None
    score = None
    if data['kind'] == 'live':
        native, score = vibe_host.verify_scored(
            host_context, digest(plan_path), data, trial, receipt,
            digest(receipt_path), snapshot_hash(tree),
        )
    sources = [plan_path, receipt_path, submission, Path(data['battery_path']).parent]
    sources.extend(Path(d['path']) for d in data['documents'])
    ensure_output(out, sources)
    result = {
        'version': 1, 'trial_id': trial_id, 'task': trial['task'], 'arm': trial['arm'],
        'plan_sha256': digest(plan_path), 'request_target': trial['conditions']['target'],
        'request_conditions': trial['conditions'], 'native_receipt': receipt,
        'receipt_path': str(receipt_path), 'receipt_sha256': digest(receipt_path),
        'submission_path': str(submission), 'submission_tree': tree,
        'submission_tree_sha256': snapshot_hash(tree),
        'normalized_receipt': native, 'host_score': score,
        'isolation': 'caller-attested' if native else 'unknown',
        'authorization': 'caller-attested' if native else 'unknown',
        'receipt_authenticity': 'caller-attested' if native else 'unknown',
        'synthetic': data['kind'] == 'synthetic' and receipt.get('kind') == 'synthetic-receipt',
        'model_runs_observed_by_script': 0,
        'note': 'No submission code executed; native receipt and host evidence require independent verification.',
    }
    out.mkdir(parents=True)
    (out / 'receipt.json').write_bytes(receipt_path.read_bytes())
    write_json(out / 'result.json', result)
    return 0


def load_records(results_dir, plan_path, data):
    results_dir = input_path(str(results_dir), Path.cwd())
    if not results_dir.is_dir():
        raise ValueError('results must be a directory')
    tree = checked_tree(results_dir)
    records = []
    for name, info in tree.items():
        if info['type'] != 'file' or Path(name).name != 'result.json':
            continue
        path = results_dir / name
        result = read_json(path)
        if not isinstance(result, dict) or result.get('plan_sha256') != digest(plan_path):
            raise ValueError(f'result plan mismatch: {name}')
        trial = get_trial(data, result.get('trial_id'))
        if result.get('task') != trial['task'] or result.get('arm') != trial['arm']:
            raise ValueError('result trial mismatch')
        if result.get('request_conditions') != trial['conditions'] or result.get('request_target') != trial['conditions']['target']:
            raise ValueError('result request conditions mismatch')
        raw_receipt = path.parent / 'receipt.json'
        if digest(raw_receipt) != result.get('receipt_sha256') or read_json(raw_receipt) != result.get('native_receipt'):
            raise ValueError('raw receipt digest mismatch')
        current_submission = input_path(result['submission_path'], Path.cwd())
        result['_submission_changed'] = checked_tree(current_submission) != result.get('submission_tree')
        result['_result_path'] = str(path)
        result['_result_sha256'] = digest(path)
        records.append(result)
    return records


def duplicate_problems(records):
    problems = []
    for key, label in (('trial_id', 'duplicate-trial'), ('runId', 'duplicate-run'), ('threadId', 'reused-thread'), ('taskId', 'duplicate-task')):
        seen = set()
        for record in records:
            value = record.get(key) if key == 'trial_id' else (record.get('normalized_receipt') or record.get('native_receipt', {})).get(key)
            if value:
                if value in seen and label not in problems:
                    problems.append(label)
                seen.add(value)
    return problems


def report_conditions(data):
    return {
        'tasks': [
            {'id': task['id'], 'prompt_sha256': task['prompt_sha256'],
             'fixture_sha256': task['fixture_sha256'], 'checker_sha256': task['checker_sha256']}
            for task in data['tasks']
        ],
        'target': data['target'],
        'required_dimensions': data['required_dimensions'],
        'permissions': data['permissions'],
        'limits': data['limits'],
        'judge_limits': data['judge_limits'],
        'wall_seconds': data['wall_seconds'],
        'budget': data['budget'],
        'statistics': data['statistics'],
    }


def report_plan(plan_path, results_dir, out, strict, judge_result=None, judge_map=None, judge_payload=None, host_context=None):
    plan_path, data = load_plan(plan_path)
    results_dir = input_path(str(results_dir), Path.cwd())
    judge_inputs = [judge_result, judge_map, judge_payload]
    if any(judge_inputs) and not all(judge_inputs):
        raise ValueError('judge result, map and payload must be supplied together')
    ensure_output(out, [plan_path, results_dir, Path(data['battery_path']).parent] + [p for p in judge_inputs if p])
    records = load_records(results_dir, plan_path, data)
    live = data['kind'] == 'live' and host_context is not None
    producer_attempts = []
    judge_attempts = []
    if live:
        _, producer_attempts, judge_attempts = vibe_host.common_evidence(
            host_context, 'report', digest(plan_path), data, {}
        )
    problems = duplicate_problems(records)
    duplicate_ids = set()
    for key in ('trial_id', 'runId', 'threadId', 'taskId'):
        values = {}
        for record in records:
            value = record.get(key) if key == 'trial_id' else (record.get('normalized_receipt') or record.get('native_receipt', {})).get(key)
            if value:
                values.setdefault(value, []).append(record['trial_id'])
        for identifiers in values.values():
            if len(identifiers) > 1:
                duplicate_ids.update(identifiers)
    by_id = {}
    for record in records:
        by_id.setdefault(record['trial_id'], record)
    rows = []
    actual_routes = []
    for trial in data['trials']:
        record = by_id.get(trial['id'])
        if not record:
            continue
        raw = record['native_receipt']
        synthetic = record.get('synthetic') is True
        if live:
            native, score = vibe_host.verify_scored(
                host_context, digest(plan_path), data, trial, raw,
                record['receipt_sha256'], record['submission_tree_sha256'],
            )
            if native != record.get('normalized_receipt') or score != record.get('host_score'):
                raise ValueError('collected host evidence changed')
            quality = score
        else:
            native = raw
            quality = raw if synthetic else {}
        status = quality.get('status', 'missing')
        if status not in RESULT_STATUSES:
            status = 'missing'
        dimensions = quality.get('dimensions')
        required = trial['conditions'].get('required_dimensions')
        valid_dimensions = (
            isinstance(required, list) and bool(required)
            and isinstance(dimensions, dict)
            and all(name in dimensions for name in required)
            and all(type(value) is bool for value in dimensions.values())
        )
        if status == 'pass' and valid_dimensions and not all(dimensions.values()):
            status = 'fail'
        if status == 'pass' and not valid_dimensions:
            status = 'skipped'
        integrity = quality.get('integrity', 'unknown')
        if trial['id'] in duplicate_ids or record.get('_submission_changed'):
            integrity = 'violation'
            if record.get('_submission_changed') and 'submission-changed' not in problems:
                problems.append('submission-changed')
        actual = {'providerInstanceId': native.get('providerInstanceId'), 'model': native.get('model'),
                  'options': native.get('options'), 'executedModel': native.get('executedModel')}
        actual_routes.append(actual)
        target = trial['conditions']['target']
        if any(actual[key] is None for key in actual):
            if 'actual-route-unknown' not in problems:
                problems.append('actual-route-unknown')
        if any(actual[key] is not None and actual[key] != target.get(key)
               for key in ('providerInstanceId', 'model', 'options')):
            if 'route-mismatch' not in problems:
                problems.append('route-mismatch')
        if not live and (raw.get('plan_sha256') is None or raw.get('checker_sha256') is None):
            if 'binding-missing' not in problems:
                problems.append('binding-missing')
        rows.append({'id': trial['id'], 'task': trial['task'], 'arm': trial['arm'],
                     'started': bool(raw.get('taskId')), 'status': status, 'integrity': integrity,
                     'required_checks': 'complete' if valid_dimensions else 'missing',
                     'judge': 'missing', 'dimensions': dimensions,
                     'evidence': record['_result_path'], 'receipt_sha256': record['receipt_sha256'],
                     'submission_tree_sha256': record['submission_tree_sha256'],
                     'failure_reason': quality.get('failure_reason')})
    judge_status = 'missing'
    judge_route = None
    if all(judge_inputs):
        judged = read_json(judge_result)
        mapping = read_json(judge_map)
        payload = read_json(judge_payload)
        expected_kind = 'host judge result' if live else 'synthetic judge result'
        if (not isinstance(judged, dict) or judged.get('kind') != expected_kind
                or judged.get('payload_sha256') != digest(judge_payload)
                or payload.get('plan_sha256') != digest(plan_path)
                or not isinstance(mapping, dict)):
            raise ValueError('judge evidence binding mismatch')
        if live:
            native_path = Path(judge_result).parent / 'native-receipt.json'
            native = read_json(native_path)
            if digest(native_path) != judged.get('native_receipt_sha256') or native != judged.get('native_receipt'):
                raise ValueError('judge native receipt changed')
            ratings_path = Path(judge_result).parent / 'ratings.json'
            if digest(ratings_path) != judged.get('ratings_sha256'):
                raise ValueError('judge ratings changed')
            checked = vibe_host.verify_judge(host_context, digest(plan_path), data,
                                              digest(judge_payload), native, digest(native_path),
                                              digest(ratings_path))
            if checked != judged.get('normalized_receipt'):
                raise ValueError('judge native evidence changed')
            judge_route = {key: checked[key] for key in ('providerInstanceId', 'model', 'options', 'executedModel')}
        ratings = judged.get('ratings')
        payload_cases = payload.get('cases')
        if not isinstance(ratings, list) or not isinstance(payload_cases, list):
            raise ValueError('invalid judge evidence')
        case_ids = {case.get('id') for case in payload_cases}
        rating_ids = {item.get('id') for item in ratings}
        if (len(case_ids) != len(payload_cases) or len(rating_ids) != len(ratings)
                or case_ids != rating_ids or case_ids != set(mapping)
                or len(set(mapping.values())) != len(mapping)):
            raise ValueError('judge evidence IDs mismatch')
        for blind_id, trial_id in mapping.items():
            expected_blind = hashlib.sha256((digest(plan_path) + trial_id).encode()).hexdigest()[:20]
            if blind_id != expected_blind:
                raise ValueError('judge anonymous mapping does not match plan')
        rows_by_id = {row['id']: row for row in rows}
        for rating in ratings:
            row = rows_by_id.get(mapping[rating['id']])
            if row is None or rating.get('deterministic_status') != row['status']:
                raise ValueError('judge deterministic result mismatch')
            score_fields = ('correctness', 'readability', 'protocol')
            if any(type(rating.get(key)) is not int or rating[key] not in (0, 1, 2)
                   for key in score_fields):
                raise ValueError('invalid judge score')
            if not isinstance(rating.get('evidence'), str) or not rating['evidence'].strip():
                raise ValueError('judge evidence required')
            row['judge'] = 'complete'
            row['judge_scores'] = {key: rating[key] for key in score_fields}
            row['judge_evidence'] = rating['evidence']
        judge_status = 'caller-attested' if live else 'synthetic-replay-only'
    known_routes = [route for route in actual_routes if all(route.get(key) is not None for key in ('providerInstanceId', 'model', 'options', 'executedModel'))]
    if len({snapshot_hash(route) for route in known_routes}) > 1:
        problems.append('cross-trial-route-inconsistent')
    slots = [{'id': t['id'], 'task': t['task'], 'arm': t['arm']} for t in data['trials']]
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp).resolve() / 'raw.json'
        write_json(source, {'kind': 'synthetic', 'trials': rows, 'expected_slots': slots})
        report(source, out, False)
        shutil.copyfile(source, out / 'raw-results.json')
    path = out / 'report.json'
    summary = read_json(path)
    summary['source'] = str(out / 'raw-results.json')
    summary['source_sha256'] = digest(out / 'raw-results.json')
    summary.update({'kind': 'caller-attested host report' if live else 'offline replay; not live evidence', 'problems': problems,
                    'plan_path': str(plan_path),
                    'plan_sha256': digest(plan_path), 'battery_sha256': data['battery_sha256'],
                    'conditions': report_conditions(data),
                    'documents': [{'name': d['name'], 'sha256': d['sha256']} for d in data['documents']],
                    'actual_routes': actual_routes, 'judge_actual_route': judge_route, 'record_locations': [r['_result_path'] for r in records],
                    'live_complete': False, 'isolation': 'caller-attested' if live else 'unknown', 'judge': judge_status})
    summary['complete'] = False
    summary['deterministic_complete'] = (
        len(rows) == len(slots)
        and not problems
        and all(row['started'] and row['integrity'] == 'ok'
                and row['status'] in ('pass', 'fail', 'timeout')
                and (row['status'] == 'timeout' or row['required_checks'] == 'complete')
                for row in rows)
    )
    if live:
        summary['model_runs'] = None
        summary['model_runs_started_by_script'] = 0
        summary['native_submitted_attempts'] = {
            'producer': len(producer_attempts), 'judge': len(judge_attempts)
        }
        summary['limitations'] = (
            '小样本；假设各上下文近似独立、组内条件稳定；缓存与时间变化可能影响结果。'
            '宿主回调证据的真实性由调用方负责核验。'
        )
        missing = []
        if judge_status != 'caller-attested':
            missing.append('independent judge')
        if not summary['deterministic_complete']:
            missing.append('complete deterministic evidence and integrity')
        summary['missing_live_evidence'] = missing
    summary['live_complete'] = bool(live and summary['deterministic_complete']
                                    and judge_status == 'caller-attested'
                                    and all(row['judge'] == 'complete' for row in rows))
    summary['complete'] = summary['live_complete']
    if not summary['deterministic_complete']:
        for task in summary['results']:
            task['difference'] = None
            task['comparison_stopped'] = True
    write_json(path, summary)
    (out / 'report.md').write_text(
        ('# 宿主回调核对的报告\n\n' if live else '# 离线结果（非 live 验证）\n\n')
        + summary['limitations'] + '\n\n'
        + json.dumps({'problems': problems, 'results': summary['results']}, ensure_ascii=False, indent=2)
        + '\n', encoding='utf-8'
    )
    return 1 if strict and not summary['live_complete'] else 0


def compare(before, after, out, strict, host_context=None):
    after = input_path(str(after), Path.cwd())
    if not after.is_dir():
        raise ValueError('after must be a report directory')
    before = Path(before)
    if '..' in before.parts:
        raise ValueError('unsafe before path')
    reject_links(before)
    before_exists = before.is_dir() and (before / 'report.json').is_file()
    ensure_output(out, [before, after])
    newer = read_json(after / 'report.json')
    older = read_json(before / 'report.json') if before_exists else None
    reasons = []
    if older is None:
        reasons.append('基线缺失')
    else:
        old_documents = older.get('documents')
        new_documents = newer.get('documents')
        if (not isinstance(old_documents, list) or not isinstance(new_documents, list)
                or any(not isinstance(doc, dict) or not isinstance(doc.get('name'), str)
                       or not isinstance(doc.get('sha256'), str) for doc in old_documents + new_documents)):
            reasons.append('document-snapshot-missing')
        elif sorted(doc['name'] for doc in old_documents) != sorted(doc['name'] for doc in new_documents):
            reasons.append('document-set-changed')
        if older.get('battery_sha256') != newer.get('battery_sha256'):
            reasons.append('battery-changed')
        if older.get('conditions') != newer.get('conditions'):
            reasons.append('conditions-changed')
            old_conditions = older.get('conditions', {})
            new_conditions = newer.get('conditions', {})
            for field in sorted(set(old_conditions) | set(new_conditions)):
                if old_conditions.get(field) != new_conditions.get(field):
                    reasons.append(f'{field}-changed')
        old_routes = older.get('actual_routes')
        new_routes = newer.get('actual_routes')
        if not old_routes or not new_routes or any(
            not isinstance(route, dict) or any(route.get(key) is None for key in ('providerInstanceId', 'model', 'options', 'executedModel'))
            for route in (old_routes or []) + (new_routes or [])
        ):
            reasons.append('actual-route-unknown')
        elif sorted(map(snapshot_hash, old_routes)) != sorted(map(snapshot_hash, new_routes)):
            reasons.append('actual-route-changed')
        for label, report_data in (('before', older), ('after', newer)):
            if report_data.get('deterministic_complete') is not True:
                reasons.append(f'{label}-incomplete')
            if any(result.get('comparison_stopped') for result in report_data.get('results', [])):
                reasons.append(f'{label}-integrity-violation')
    live = False
    if host_context is not None and older is not None:
        for label, directory, report_data in (('before', before, older), ('after', after, newer)):
            plan_path, plan_data = load_plan(report_data.get('plan_path'))
            plan_sha = digest(plan_path)
            if (plan_data['kind'] != 'live' or report_data.get('plan_sha256') != plan_sha
                    or report_data.get('live_complete') is not True):
                raise ValueError(f'{label} live plan or report incomplete')
            if (report_data.get('conditions') != report_conditions(plan_data)
                    or report_data.get('battery_sha256') != plan_data['battery_sha256']):
                raise ValueError('report conditions do not match frozen plan')
            expected_docs = [{'name': doc['name'], 'sha256': doc['sha256']} for doc in plan_data['documents']]
            if report_data.get('documents') != expected_docs:
                raise ValueError('report document snapshot mismatch')
            evidence, _, _ = vibe_host.common_evidence(
                host_context, 'compare', plan_sha, plan_data,
                {'report_sha256': digest(directory / 'report.json')},
            )
            if (evidence.get('report_sha256') != digest(directory / 'report.json')
                    or evidence.get('report_complete') is not True):
                raise ValueError('host report evidence missing')
        if older.get('judge_actual_route') is None or newer.get('judge_actual_route') is None:
            reasons.append('judge-route-unknown')
        elif older['judge_actual_route'] != newer['judge_actual_route']:
            reasons.append('judge-route-changed')
        if older.get('documents') == newer.get('documents'):
            reasons.append('documents-unchanged')
        live = not reasons
    result = {
        'kind': 'caller-attested live comparison' if live else 'synthetic or incomplete comparison',
        'model_runs': None if live else 0, 'model_runs_started_by_script': 0,
        'before': {'path': str(before), 'sha256': digest(before / 'report.json'), 'results': older.get('results')} if older else None,
        'after': {'path': str(after), 'sha256': digest(after / 'report.json'), 'results': newer.get('results')},
        'documents_before': older.get('documents') if older else None,
        'documents_after': newer.get('documents'),
        'documents_changed': older is not None and older.get('documents') != newer.get('documents'),
        'synthetic_comparable': not reasons and not live, 'live_attribution': live,
        'reasons': reasons, 'limitations': ('宿主回调证据由调用方负责核验；两批预算独立。' if live
                                           else '真实路由、隔离或授权未认证或不可比；两批预算独立。'),
    }
    out.mkdir(parents=True)
    write_json(out / 'compare.json', result)
    (out / 'compare.md').write_text('# 比较报告\n\n' + json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 1 if strict and not live else 0


def judge_prepare(plan_path, results_dir, out, host_context=None):
    plan_path, data = load_plan(plan_path)
    live = data['kind'] == 'live'
    if live:
        vibe_host.allow_judge_prepare(host_context, digest(plan_path), data)
    if data.get('approval_status') != 'approved':
        raise ValueError('plan approval status is absent or revoked')
    records = load_records(results_dir, plan_path, data)
    if not records or duplicate_problems(records):
        raise ValueError('judge input missing or contains duplicate trial/session')
    sources = [plan_path, Path(results_dir), Path(data['battery_path']).parent]
    sources.extend(Path(record['submission_path']) for record in records)
    ensure_output(out, sources)
    labels = re.compile(r'\b(control|treatment)\b', re.IGNORECASE)
    cases = []
    mapping = {}
    for record in records:
        if not live and not record.get('synthetic'):
            raise ValueError('live submissions cannot be placed in synthetic judge payload')
        trial = get_trial(data, record['trial_id'])
        task = next(item for item in data['tasks'] if item['id'] == trial['task'])
        public = Path(task['public'])
        if checked_tree(public) != task['public_tree']:
            raise ValueError('public input changed')
        submission = input_path(record['submission_path'], Path.cwd())
        if checked_tree(submission) != record['submission_tree']:
            raise ValueError('submission changed after collection')
        files = []
        for name, entry in sorted(record['submission_tree'].items()):
            if entry['type'] != 'file':
                continue
            content = (submission / name).read_bytes().decode('utf-8')
            if labels.search(name) or labels.search(content) or record['trial_id'] in content:
                raise ValueError('submission contains identifying labels; anonymous judge blocked')
            files.append({'path': name, 'content': content})
        contracts = []
        for name, entry in sorted(task['public_tree'].items()):
            if entry['type'] == 'file' and Path(name).name == 'contract.md':
                contracts.append((public / name).read_text(encoding='utf-8'))
        receipt = record['native_receipt']
        if live:
            native, score = vibe_host.verify_scored(
                host_context, digest(plan_path), data, trial, receipt,
                record['receipt_sha256'], record['submission_tree_sha256'],
            )
            if native != record.get('normalized_receipt') or score != record.get('host_score'):
                raise ValueError('collected host evidence changed')
            receipt = score
        dimensions = receipt.get('dimensions')
        if labels.search(json.dumps(dimensions, ensure_ascii=False)):
            raise ValueError('deterministic evidence contains identifying labels')
        status = receipt.get('status', 'missing')
        if status == 'pass':
            required = trial['conditions'].get('required_dimensions')
            valid = (
                isinstance(required, list) and bool(required)
                and isinstance(dimensions, dict)
                and all(name in dimensions for name in required)
                and all(type(value) is bool for value in dimensions.values())
            )
            if not valid:
                status = 'skipped'
            elif any(value is False for value in dimensions.values()):
                status = 'fail'
        blind = hashlib.sha256((digest(plan_path) + record['trial_id']).encode()).hexdigest()[:20]
        mapping[blind] = record['trial_id']
        cases.append({'id': blind, 'contracts': contracts, 'artifacts': files,
                      'deterministic_status': status, 'deterministic_dimensions': dimensions})
    random.Random(int(digest(plan_path)[:16], 16)).shuffle(cases)
    payload = {'kind': 'host-judge-batch' if live else 'synthetic-judge-batch',
               'model_runs': None if live else 0, 'model_runs_started_by_script': 0,
               'plan_sha256': digest(plan_path),
               'rubric': 'Score correctness, readability and protocol 0, 1 or 2 with location evidence. Do not change deterministic status.',
               'cases': cases}
    encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if len(encoded) > 262144:
        raise ValueError('judge batch exceeds offline capacity; no automatic split')
    out.mkdir(parents=True)
    write_json(out / 'payload.json', payload)
    write_json(out / 'private-map.json', mapping)
    return 0


def judge_collect(payload_path, ratings_path, out, host_context=None, plan_path=None, native_receipt_path=None):
    payload_path = input_path(str(payload_path), Path.cwd())
    ratings_path = input_path(str(ratings_path), Path.cwd())
    payload = read_json(payload_path)
    ratings = read_json(ratings_path)
    live = payload.get('kind') == 'host-judge-batch'
    native = None
    raw_judge = None
    protected = [payload_path, ratings_path]
    if live:
        if plan_path is None or native_receipt_path is None:
            raise ValueError('host judge plan and native receipt required')
        plan_path, plan_data = load_plan(plan_path)
        native_receipt_path = input_path(str(native_receipt_path), Path.cwd())
        if payload.get('plan_sha256') != digest(plan_path):
            raise ValueError('judge payload plan mismatch')
        raw_judge = read_json(native_receipt_path)
        native = vibe_host.verify_judge(host_context, digest(plan_path), plan_data,
                                        digest(payload_path), raw_judge, digest(native_receipt_path),
                                        digest(ratings_path))
        protected += [plan_path, native_receipt_path]
    elif payload.get('kind') != 'synthetic-judge-batch':
        raise ValueError('invalid judge payload kind')
    expected_kind = 'host-judge-result' if live else 'synthetic-judge-result'
    if ratings.get('kind') != expected_kind:
        raise ValueError('judge result kind mismatch')
    ensure_output(out, protected)
    cases = {case['id']: case for case in payload['cases']}
    if len(cases) != len(payload['cases']) or not isinstance(ratings.get('ratings'), list):
        raise ValueError('invalid judge batch')
    seen = set()
    collected = []
    for item in ratings['ratings']:
        if not isinstance(item, dict) or item.get('id') not in cases or item['id'] in seen:
            raise ValueError('invalid or duplicate rating')
        if any(type(item.get(key)) is not int or item[key] not in (0, 1, 2) for key in ('correctness', 'readability', 'protocol')):
            raise ValueError('judge scores must be 0, 1 or 2')
        if not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
            raise ValueError('judge evidence required')
        seen.add(item['id'])
        collected.append({**item, 'deterministic_status': cases[item['id']]['deterministic_status']})
    if seen != set(cases):
        raise ValueError('judge ratings missing')
    out.mkdir(parents=True)
    if live:
        (out / 'native-receipt.json').write_bytes(native_receipt_path.read_bytes())
        (out / 'ratings.json').write_bytes(ratings_path.read_bytes())
    write_json(out / 'judge-result.json', {'kind': 'host judge result' if live else 'synthetic judge result',
               'model_runs': None if live else 0, 'model_runs_started_by_script': 0,
               'live_verified': False, 'payload_sha256': digest(payload_path),
               'ratings_sha256': digest(ratings_path), 'ratings': collected,
               'native_receipt': raw_judge, 'normalized_receipt': native,
               'native_receipt_sha256': digest(native_receipt_path) if live else None})
    return 0


def inspect_tree(baseline, submission, access_log, allowed, out):
    baseline = input_path(str(baseline), Path.cwd())
    submission = input_path(str(submission), Path.cwd())
    access_log = input_path(str(access_log), Path.cwd())
    ensure_output(out, [baseline, submission, access_log])
    before, after = checked_tree(baseline), checked_tree(submission)
    paths = []
    for value in allowed:
        path = Path(value)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ValueError('invalid allowed path')
        paths.append(path.as_posix())
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    violations = [name for name in changed if not any(name == item or name.startswith(item + '/') for item in paths)]
    raw = read_json(access_log)
    if not isinstance(raw, dict) or not isinstance(raw.get('events'), list):
        raise ValueError('invalid access log')
    observed = []
    for event in raw['events']:
        if not isinstance(event, dict):
            raise ValueError('invalid access event')
        if event.get('action') == 'network' or event.get('scope') in ('private', 'other-arm', 'target-docs-control'):
            observed.append(event)
    out.mkdir(parents=True)
    write_json(out / 'inspection.json', {'kind': 'offline inspection', 'baseline_sha256': snapshot_hash(before),
               'submission_sha256': snapshot_hash(after), 'changed': changed, 'unauthorized_changes': violations,
               'forbidden_access_observed': observed, 'access_log_sha256': digest(access_log),
               'access_log_authenticity': 'unknown', 'isolation': 'unknown', 'live_verified': False})
    return 0


def control_handoff(plan_path, results_dir, out, host_context=None):
    plan_path, data = load_plan(plan_path)
    records = load_records(results_dir, plan_path, data)
    ensure_output(out, [plan_path, Path(results_dir), Path(data['battery_path']).parent])
    observed = sorted({record['native_receipt'].get('taskId') for record in records
                       if isinstance(record['native_receipt'].get('taskId'), str)
                       and record['native_receipt']['taskId']})
    verified_ids = []
    running = []
    used_slots = None
    if host_context is not None and data['kind'] == 'live':
        _, attempts, judges = vibe_host.common_evidence(
            host_context, 'control_handoff', digest(plan_path), data, {}
        )
        all_attempts = attempts + judges
        verified_ids = sorted(item['taskId'] for item in all_attempts
                              if isinstance(item.get('taskId'), str) and item['taskId'])
        running = sorted(item['taskId'] for item in all_attempts
                         if item.get('status') in ('running', 'unknown')
                         and isinstance(item.get('taskId'), str) and item['taskId'])
        used_slots = len(attempts)
    out.mkdir(parents=True)
    write_json(out / 'handoff.json', {
        'kind': 'host operation suggestions only', 'unverified_observed_taskIds': observed,
        'known_batch_taskIds': verified_ids, 'candidate_cancel_taskIds': running,
        'used_slots': used_slots, 'collected_records': len(records),
        'planned_slots': len(data['trials']), 'judge_budget': data['budget']['judge_runs'],
        'automatic_retries': 0,
        'native_authenticity': 'caller-attested' if verified_ids else 'unknown',
        'hard_limit_capability': 'unknown',
        'guidance': ('Host must verify actual ownership and status. Never resubmit an unknown result. '
                     'timeoutMs is a wait, not an execution limit.'),
    })
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    o = sub.add_parser('oracle')
    o.add_argument('--battery', type=Path, required=True)
    o.add_argument('--out', type=Path, required=True)
    pl = sub.add_parser('plan')
    pl.add_argument('--config', type=Path, required=True)
    pl.add_argument('--out', type=Path, required=True)
    pr = sub.add_parser('prepare')
    pr.add_argument('--plan', type=Path, required=True)
    pr.add_argument('--trial-id', required=True)
    pr.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('collect')
    c.add_argument('--results', type=Path)
    c.add_argument('--plan', type=Path)
    c.add_argument('--trial-id')
    c.add_argument('--receipt', type=Path)
    c.add_argument('--submission', type=Path)
    c.add_argument('--out', type=Path, required=True)
    r = sub.add_parser('report')
    r.add_argument('--results', type=Path, required=True)
    r.add_argument('--plan', type=Path)
    r.add_argument('--judge-result', type=Path)
    r.add_argument('--judge-map', type=Path)
    r.add_argument('--judge-payload', type=Path)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--strict', action='store_true')
    it = sub.add_parser('inspect-tree')
    it.add_argument('--baseline', type=Path, required=True)
    it.add_argument('--submission', type=Path, required=True)
    it.add_argument('--access-log', type=Path, required=True)
    it.add_argument('--allow', action='append', default=[])
    it.add_argument('--out', type=Path, required=True)
    hand = sub.add_parser('control-handoff')
    hand.add_argument('--plan', type=Path, required=True)
    hand.add_argument('--results', type=Path, required=True)
    hand.add_argument('--out', type=Path, required=True)
    jp = sub.add_parser('judge-prepare')
    jp.add_argument('--plan', type=Path, required=True)
    jp.add_argument('--results', type=Path, required=True)
    jp.add_argument('--out', type=Path, required=True)
    jc = sub.add_parser('judge-collect')
    jc.add_argument('--payload', type=Path, required=True)
    jc.add_argument('--ratings', type=Path, required=True)
    jc.add_argument('--out', type=Path, required=True)
    cmp = sub.add_parser('compare')
    cmp.add_argument('--before', type=Path, required=True)
    cmp.add_argument('--after', type=Path, required=True)
    cmp.add_argument('--out', type=Path, required=True)
    cmp.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'oracle':
            return oracle(args.battery, args.out)
        if args.command == 'inspect-tree':
            return inspect_tree(args.baseline, args.submission, args.access_log, args.allow, args.out)
        if args.command == 'control-handoff':
            return control_handoff(args.plan, args.results, args.out)
        if args.command == 'judge-prepare':
            return judge_prepare(args.plan, args.results, args.out)
        if args.command == 'judge-collect':
            return judge_collect(args.payload, args.ratings, args.out)
        if args.command == 'compare':
            return compare(args.before, args.after, args.out, args.strict)
        if args.command == 'plan':
            return plan(args.config, args.out)
        if args.command == 'prepare':
            return prepare(args.plan, args.trial_id, args.out)
        if args.command == 'collect':
            if args.plan and args.trial_id and args.receipt and args.submission and not args.results:
                return collect_trial(args.plan, args.trial_id, args.receipt, args.submission, args.out)
            if args.results and not any((args.plan, args.trial_id, args.receipt, args.submission)):
                return collect(args.results, args.out)
            raise ValueError('collect requires --results or all of --plan/--trial-id/--receipt/--submission')
        if args.plan:
            return report_plan(args.plan, args.results, args.out, args.strict,
                               args.judge_result, args.judge_map, args.judge_payload)
        if any((args.judge_result, args.judge_map, args.judge_payload)):
            raise ValueError('judge inputs require --plan')
        return report(args.results, args.out, args.strict)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
