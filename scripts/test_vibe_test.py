import importlib.util
import copy
import json
import math
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vibe_test.py'
BATTERY = ROOT / 'examples/vibe-battery-v1/battery.json'

class CoreTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('vibe_test', SCRIPT)
        self.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.core)

    def test_fixed_statistics(self):
        treatment = self.core.wilson(2, 3)
        control = self.core.wilson(1, 3)
        low, high = self.core.newcombe(2, 3, 1, 3)
        self.assertAlmostEqual(treatment[0], .2076596008, places=9)
        self.assertAlmostEqual(control[1], .7923403992, places=9)
        self.assertAlmostEqual(low, -.3158006844, places=9)
        self.assertAlmostEqual(high, .7177751119, places=9)

    def test_invalid_json_and_output_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp).resolve() / 'bad.json'
            p.write_bytes(b'\xff')
            with self.assertRaises(ValueError):
                self.core.read_json(p)
            with self.assertRaises(ValueError):
                self.core.check_output(BATTERY, BATTERY.parent)

    def test_oracle_and_relaxed_checker_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp).resolve() / 'oracle'
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'oracle', '--battery', str(BATTERY), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads((out / 'oracle.json').read_text())
            self.assertTrue(result['passed'])
            self.assertEqual(result['model_runs'], 0)
            self.assertGreaterEqual(len(result['cases']), 11)

    def test_relaxed_checkers_are_rejected(self):
        for task in ('B01', 'B02'):
            with self.subTest(task=task), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                battery = root / 'battery'
                shutil.copytree(BATTERY.parent, battery)
                checker = battery / task / 'private/checker.py'
                source = checker.read_text(encoding='utf-8')
                if task == 'B01':
                    source = source.replace("checks[name] = proc.returncode == 0 and (('note' not in record) if note is None else record.get('note') == note)", "checks[name] = proc.returncode == 0")
                else:
                    source = source.replace("    return {'dimensions': checks,", "    checks = {'json': True}\n    return {'dimensions': checks,")
                checker.write_text(source, encoding='utf-8')
                manifest = battery / 'battery.json'
                data = json.loads(manifest.read_text())
                data['assets'][f'{task}/private/checker.py'] = hashlib.sha256(checker.read_bytes()).hexdigest()
                manifest.write_text(json.dumps(data), encoding='utf-8')
                out = root / 'out'
                proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'oracle', '--battery', str(manifest), '--out', str(out)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                result = json.loads((out / 'oracle.json').read_text())
                self.assertEqual(result['model_runs'], 0)
                self.assertFalse(result['passed'])
                target = 'parser_only' if task == 'B01' else 'empty'
                item = next(c for c in result['cases'] if c['task'] == task and c['case'] == target)
                self.assertFalse(item['matched'])

    def test_b02_public_observation_contract(self):
        battery_root = BATTERY.parent
        checker_path = battery_root / 'B02/private/checker.py'
        spec = importlib.util.spec_from_file_location('b02_checker', checker_path)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        public = battery_root / 'B02/public'
        reference_path = battery_root / 'B02/private/reference/findings.json'
        reference = json.loads(reference_path.read_text(encoding='utf-8'))

        def assess(findings):
            with tempfile.TemporaryDirectory() as temp:
                submission = Path(temp).resolve()
                (submission / 'findings.json').write_text(
                    json.dumps(findings, ensure_ascii=False), encoding='utf-8'
                )
                return checker.check(public, submission)['dimensions']

        equivalent = copy.deepcopy(reference)
        equivalent[0]['observation'] = {'actual': True, 'expected': False}
        equivalent[0]['impact'] = 'A read can change persisted bytes.'
        equivalent[0]['suggestion'] = 'Preserve the input when reading.'
        equivalent[1]['impact'] = 'Consumers receive IDs in the wrong order.'
        equivalent.reverse()
        with self.subTest('boolean aliases and reordering'):
            self.assertTrue(all(assess(equivalent).values()))
        mixed = copy.deepcopy(equivalent)
        mixed[1]['observation'] = {'expected': 'unchanged', 'actual': True}
        with self.subTest('mixed aliases'):
            self.assertTrue(all(assess(mixed).values()))

        checks = [
            ('wrong write observation', lambda f: f[0]['observation'].update(actual=False), 'write'),
            ('wrong order observation', lambda f: f[1]['observation'].update(actual=['a', 'z']), 'ordering'),
            ('invalid observation type', lambda f: f[0]['observation'].update(actual=1), 'schema'),
            ('nonpositive range', lambda f: f[0].update(line_start=0), 'schema'),
            ('reversed range', lambda f: f[0].update(line_start=8, line_end=7), 'schema'),
            ('boolean line number', lambda f: f[0].update(line_start=True), 'schema'),
            ('range outside symbol', lambda f: f[0].update(line_start=1, line_end=100), 'write'),
            ('format false positive', lambda f: f.append(dict(f[0], symbol='format_entry', category='other', line_start=16, line_end=16)), 'no_false_positive'),
        ]
        for label, mutate, dimension in checks:
            with self.subTest(label):
                candidate = copy.deepcopy(reference)
                mutate(candidate)
                self.assertFalse(assess(candidate)[dimension])

    def test_asset_integrity_and_path_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            battery = root / 'battery'
            shutil.copytree(BATTERY.parent, battery)
            manifest = battery / 'battery.json'
            frozen = battery / 'B02/public/input/schema.json'
            frozen_bytes = frozen.read_bytes()
            occupied = root / 'occupied'
            occupied.mkdir()
            sentinel = occupied / 'keep'
            sentinel.write_bytes(b'preserve')

            def run(out):
                return subprocess.run(
                    [sys.executable, '-B', str(SCRIPT), 'oracle', '--battery', str(manifest), '--out', str(out)],
                    capture_output=True, text=True,
                )

            self.assertEqual(run(occupied).returncode, 2)
            self.assertEqual(sentinel.read_bytes(), b'preserve')
            self.assertEqual(run(battery / 'new-output').returncode, 2)
            alias_parent = root / 'alias'
            alias_parent.mkdir()
            disguised_output = alias_parent / '..' / 'battery' / 'disguised-output'
            self.assertEqual(run(disguised_output).returncode, 2)
            self.assertFalse((battery / 'disguised-output').exists())
            self.assertEqual(frozen.read_bytes(), frozen_bytes)
            frozen.write_bytes(frozen_bytes + b' ')
            self.assertEqual(run(root / 'bad-hash-output').returncode, 2)
            self.assertFalse((root / 'bad-hash-output').exists())
            frozen.write_bytes(frozen_bytes)
            link = root / 'link'
            link.symlink_to(root, target_is_directory=True)
            self.assertEqual(run(link / 'escaped').returncode, 2)
            self.assertEqual(frozen.read_bytes(), frozen_bytes)

    def test_integrity_violation_stops_entire_battery_comparison(self):
        source = ROOT / 'examples/vibe-battery-v1/private/report-cases/complete.json'
        data = json.loads(source.read_text(encoding='utf-8'))
        data['trials'][0]['integrity'] = 'violation'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            results = root / 'results.json'
            results.write_text(json.dumps(data), encoding='utf-8')
            out = root / 'report'
            proc = subprocess.run(
                [sys.executable, '-B', str(SCRIPT), 'report', '--results', str(results), '--out', str(out)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
            self.assertFalse(report['complete'])
            self.assertEqual(sum(item['integrity_violations'] for item in report['results']), 1)
            for task in report['results']:
                with self.subTest(task=task['task']):
                    self.assertTrue(task['comparison_stopped'])
                    self.assertIsNone(task['difference'])

    def test_strict_incomplete_report_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp).resolve() / 'report'
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'report', '--results', str(ROOT / 'examples/vibe-battery-v1/private/report-cases/incomplete.json'), '--out', str(out), '--strict'], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            data = json.loads((out / 'report.json').read_text())
            self.assertFalse(data['complete'])

class DeliveryTests(unittest.TestCase):

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)], capture_output=True, text=True)

    def test_plan_fairness_prepare_and_live_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'synthetic',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 3,
                'budget': {'producer_runs': 12, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {'effort': 'test'}},
                'permissions': ['read-public'],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
                'approval_ref': 'synthetic-only',
            }
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            plan_dir = root / 'plan'
            proc = self.run_cli('plan', '--config', config_path, '--out', plan_dir)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan_path = plan_dir / 'plan.json'
            plan = json.loads(plan_path.read_text())
            self.assertEqual(len(plan['trials']), 12)
            self.assertEqual(plan['budget']['judge_runs'], 1)
            for first, second in zip(plan['trials'][::2], plan['trials'][1::2]):
                self.assertEqual((first['task'], first['repetition']), (second['task'], second['repetition']))
                self.assertEqual({first['arm'], second['arm']}, {'control', 'treatment'})
                self.assertEqual(first['conditions'], second['conditions'])
            out = root / 'prepared'
            proc = self.run_cli('prepare', '--plan', plan_path, '--trial-id', plan['trials'][0]['id'], '--out', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((out / 'payload.json').is_file())
            self.assertFalse(any(('private' in p.relative_to(out).parts for p in out.rglob('*'))))
            self.assertFalse((out / 'documents').exists())
            altered = copy.deepcopy(plan)
            altered['trials'][1]['conditions']['limits']['seconds'] = 1
            altered_path = root / 'altered.json'
            altered_path.write_text(json.dumps(altered))
            blocked_tamper = root / 'blocked-tamper'
            proc = self.run_cli('prepare', '--plan', altered_path, '--trial-id', plan['trials'][0]['id'], '--out', blocked_tamper)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(blocked_tamper.exists())
            config['kind'] = 'live'
            config['approval_status'] = 'approved'
            config['verified'] = True
            config_path.write_text(json.dumps(config))
            live_plan = root / 'live-plan'
            proc = self.run_cli('plan', '--config', config_path, '--out', live_plan)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            blocked = root / 'blocked'
            proc = self.run_cli('prepare', '--plan', live_plan / 'plan.json', '--trial-id', plan['trials'][0]['id'], '--out', blocked)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(blocked.exists())

    def test_collect_and_report_preserve_unknown_and_reject_duplicate_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'synthetic',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
            }
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            proc = self.run_cli('plan', '--config', config_path, '--out', root / 'plan')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan_path = root / 'plan/plan.json'
            plan = json.loads(plan_path.read_text())
            results = root / 'results'
            results.mkdir()
            submission = root / 'submission'
            submission.mkdir()
            (submission / 'artifact.txt').write_text('offline synthetic')
            for index, trial in enumerate(plan['trials'][:2]):
                receipt = {
                    'kind': 'synthetic-receipt',
                    'trial_id': trial['id'],
                    'taskId': f'task-{index}',
                    'runId': 'duplicate-run',
                    'threadId': 'reused-thread',
                    'providerInstanceId': 'wrong-provider',
                    'model': 'fixture',
                    'options': {},
                    'executedModel': None,
                    'status': 'pass',
                    'dimensions': {'probe': True},
                    'integrity': 'unknown',
                    'start': None,
                    'end': None,
                }
                path = root / f'receipt-{index}.json'
                path.write_text(json.dumps(receipt))
                proc = self.run_cli('collect', '--plan', plan_path, '--trial-id', trial['id'], '--receipt', path, '--submission', submission, '--out', results / f'c{index}')
                self.assertEqual(proc.returncode, 0, proc.stderr)
                recorded = json.loads((results / f'c{index}' / 'result.json').read_text())
                self.assertIsNone(recorded['native_receipt']['executedModel'])
                self.assertEqual(recorded['native_receipt']['runId'], 'duplicate-run')
                self.assertEqual(recorded['isolation'], 'unknown')
            report = root / 'report'
            proc = self.run_cli('report', '--plan', plan_path, '--results', results, '--out', report, '--strict')
            self.assertNotEqual(proc.returncode, 0)
            output = json.loads((report / 'report.json').read_text())
            self.assertIn('duplicate-run', output['problems'])
            self.assertIn('reused-thread', output['problems'])
            self.assertIn('actual-route-unknown', output['problems'])
            self.assertIn('route-mismatch', output['problems'])
            self.assertFalse(output['live_complete'])

    def test_compare_distinguishes_missing_and_changed_conditions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            before = root / 'before'
            before.mkdir()
            after = root / 'after'
            after.mkdir()
            base = {
                'kind': 'synthetic replay; not live evidence',
                'live_complete': False,
                'battery_sha256': 'a',
                'deterministic_complete': True,
                'conditions': {'checker': 'a', 'target': {'model': 'm'}},
                'actual_routes': [{'providerInstanceId': 'synthetic', 'model': 'm', 'options': {}, 'executedModel': 'm'}],
                'documents': [{'name': 'doc', 'sha256': 'old'}],
                'results': [],
            }
            (before / 'report.json').write_text(json.dumps(base))
            updated = copy.deepcopy(base)
            updated['documents'][0]['sha256'] = 'new'
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'same')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads((root / 'same/compare.json').read_text())
            self.assertTrue(result['synthetic_comparable'])
            self.assertFalse(result['live_attribution'])
            updated['deterministic_complete'] = False
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'incomplete')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('after-incomplete', json.loads((root / 'incomplete/compare.json').read_text())['reasons'])
            updated['deterministic_complete'] = True
            updated['conditions']['checker'] = 'changed'
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'changed', '--strict')
            self.assertNotEqual(proc.returncode, 0)
            result = json.loads((root / 'changed/compare.json').read_text())
            self.assertIn('conditions-changed', result['reasons'])
            updated = copy.deepcopy(base)
            updated['documents'][0]['name'] = 'other-doc'
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'changed-doc-set')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('document-set-changed', json.loads((root / 'changed-doc-set/compare.json').read_text())['reasons'])
            updated = copy.deepcopy(base)
            updated['conditions']['target']['model'] = 'other-model'
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'model-change')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('target-changed', json.loads((root / 'model-change/compare.json').read_text())['reasons'])
            updated = copy.deepcopy(base)
            updated['actual_routes'][0]['executedModel'] = 'other-model'
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'actual-model-change')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('actual-route-changed', json.loads((root / 'actual-model-change/compare.json').read_text())['reasons'])
            updated = copy.deepcopy(base)
            updated['actual_routes'][0]['executedModel'] = None
            (after / 'report.json').write_text(json.dumps(updated))
            proc = self.run_cli('compare', '--before', before, '--after', after, '--out', root / 'unknown-model')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('actual-route-unknown', json.loads((root / 'unknown-model/compare.json').read_text())['reasons'])
            proc = self.run_cli('compare', '--before', root / 'missing', '--after', after, '--out', root / 'missing-report')
            self.assertEqual(proc.returncode, 0)
            result = json.loads((root / 'missing-report/compare.json').read_text())
            self.assertIn('基线缺失', result['reasons'])
            alias=root/'missing-alias'
            proc=self.run_cli('compare','--before',alias,'--after',after,'--out',alias)
            self.assertNotEqual(proc.returncode,0)
            self.assertFalse(alias.exists())

    def test_judge_replay_is_anonymous_and_cannot_promote_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            payload = {'kind': 'synthetic-judge-batch', 'cases': [{'id': 'blind-1', 'deterministic_status': 'fail'}]}
            payload_path = root / 'judge.json'
            payload_path.write_text(json.dumps(payload))
            ratings = {'kind': 'synthetic-judge-result', 'ratings': [{'id': 'blind-1', 'correctness': 2, 'readability': 2, 'protocol': 2, 'evidence': 'artifact line 1'}]}
            ratings_path = root / 'ratings.json'
            ratings_path.write_text(json.dumps(ratings))
            out = root / 'judge-result'
            proc = self.run_cli('judge-collect', '--payload', payload_path, '--ratings', ratings_path, '--out', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads((out / 'judge-result.json').read_text())
            self.assertEqual(result['ratings'][0]['deterministic_status'], 'fail')
            self.assertFalse(result['live_verified'])
            ratings['ratings'][0]['correctness'] = 3
            ratings_path.write_text(json.dumps(ratings))
            proc = self.run_cli('judge-collect', '--payload', payload_path, '--ratings', ratings_path, '--out', root / 'bad')
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((root / 'bad').exists())

    def test_alternate_battery_docs_and_refusal_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            battery = root / 'other-battery'
            shutil.copytree(BATTERY.parent, battery)
            manifest = battery / 'battery.json'
            data = json.loads(manifest.read_text())
            data['tasks'][0]['id'] = 'CodeZ'
            data['tasks'][1]['id'] = 'ReviewZ'
            manifest.write_text(json.dumps(data))
            doc = root / 'another.md'
            doc.write_text('Synthetic alternate document')
            config = {
                'kind': 'synthetic',
                'battery': str(manifest),
                'documents': [str(doc)],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {}},
                'permissions': ['public-only'],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
            }
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            out = root / 'plan'
            proc = self.run_cli('plan', '--config', path, '--out', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan = json.loads((out / 'plan.json').read_text())
            self.assertEqual({t['task'] for t in plan['trials']}, {'CodeZ', 'ReviewZ'})
            for trial in plan['trials'][:2]:
                target = root / trial['arm']
                proc = self.run_cli('prepare', '--plan', out / 'plan.json', '--trial-id', trial['id'], '--out', target)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual((target / 'documents' / 'another.md').exists(), trial['arm'] == 'treatment')
            tampered = copy.deepcopy(plan)
            tampered['documents'][0]['name'] = '../../victim'
            forged = root / 'forged-plan.json'
            forged.write_text(json.dumps(tampered))
            victim = root / 'victim'
            victim.write_text('preserve')
            treatment = next((t for t in plan['trials'] if t['arm'] == 'treatment'))
            proc = self.run_cli('prepare', '--plan', forged, '--trial-id', treatment['id'], '--out', root / 'forged-output')
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(victim.read_text(), 'preserve')
            for approval in ('unapproved', 'revoked'):
                config['approval_status'] = approval
                path.write_text(json.dumps(config))
                new_plan = root / f'plan-{approval}'
                proc = self.run_cli('plan', '--config', path, '--out', new_plan)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                destination = root / f'blocked-{approval}'
                proc = self.run_cli('prepare', '--plan', new_plan / 'plan.json', '--trial-id', plan['trials'][0]['id'], '--out', destination)
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse(destination.exists())

    def test_tree_audit_never_certifies_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            before = root / 'before'
            after = root / 'after'
            before.mkdir()
            after.mkdir()
            (before / 'protected.txt').write_text('before')
            (after / 'protected.txt').write_text('changed')
            log = root / 'access.json'
            log.write_text(json.dumps({'events': [], 'complete': True, 'verified': True}))
            out = root / 'audit'
            proc = self.run_cli('inspect-tree', '--baseline', before, '--submission', after, '--access-log', log, '--out', out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((out / 'inspection.json').read_text())
            self.assertEqual(data['unauthorized_changes'], ['protected.txt'])
            self.assertEqual(data['isolation'], 'unknown')
            self.assertFalse(data['live_verified'])

    def test_incomplete_batch_does_not_publish_difference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'synthetic',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
                'required_dimensions': {'B01': ['probe'], 'B02': ['probe']},
            }
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            self.assertEqual(self.run_cli('plan', '--config', config_path, '--out', root / 'plan').returncode, 0)
            plan_path = root / 'plan/plan.json'
            plan = json.loads(plan_path.read_text())
            plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            sub = root / 'submission'
            sub.mkdir()
            (sub / 'x.txt').write_text('synthetic')
            results = root / 'results'
            results.mkdir()
            for index, trial in enumerate(plan['trials']):
                receipt = {
                    'kind': 'synthetic-receipt',
                    'trial_id': trial['id'],
                    'taskId': f't{index}',
                    'runId': f'r{index}',
                    'threadId': f'h{index}',
                    'providerInstanceId': 'synthetic',
                    'model': 'fixture',
                    'options': {},
                    'executedModel': 'fixture',
                    'status': 'facility_failure' if index == 0 else 'pass',
                    'dimensions': {'probe': True},
                    'integrity': 'ok',
                    'plan_sha256': plan_hash,
                    'checker_sha256': trial['conditions']['checker_sha256'],
                }
                receipt_path = root / f'r{index}.json'
                receipt_path.write_text(json.dumps(receipt))
                proc = self.run_cli('collect', '--plan', plan_path, '--trial-id', trial['id'], '--receipt', receipt_path, '--submission', sub, '--out', results / f'item{index}')
                self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = self.run_cli('report', '--plan', plan_path, '--results', results, '--out', root / 'report')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((root / 'report/report.json').read_text())
            self.assertFalse(data['deterministic_complete'])
            self.assertTrue(all((item['difference'] is None for item in data['results'])))
            results2 = root / 'results2'
            results2.mkdir()
            for index, trial in enumerate(plan['trials']):
                receipt_path = root / f'r{index}.json'
                receipt = json.loads(receipt_path.read_text())
                receipt['status'] = 'timeout' if index == 1 else 'pass'
                receipt['integrity'] = 'violation' if index == 0 else 'ok'
                receipt_path.write_text(json.dumps(receipt))
                proc = self.run_cli('collect', '--plan', plan_path, '--trial-id', trial['id'], '--receipt', receipt_path, '--submission', sub, '--out', results2 / f'item{index}')
                self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = self.run_cli('report', '--plan', plan_path, '--results', results2, '--out', root / 'report2')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((root / 'report2/report.json').read_text())
            self.assertEqual(sum((item['integrity_violations'] for item in data['results'])), 1)
            self.assertTrue(all((item['comparison_stopped'] and item['difference'] is None for item in data['results'])))
            self.assertTrue(any((row['status'] == 'timeout' for row in data['raw_trials'])))
            first = next((item for item in data['results'] if item['task'] == plan['trials'][1]['task']))
            timeout_arm = first['arms'][plan['trials'][1]['arm']]
            self.assertEqual((timeout_arm['quality_denominator'], timeout_arm['pass']), (1, 0))

    def test_missing_required_dimension_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'synthetic',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
                'required_dimensions': {'B01': ['probe', 'read_only'], 'B02': ['probe', 'read_only']},
            }
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            self.assertEqual(self.run_cli('plan', '--config', config_path, '--out', root / 'plan').returncode, 0)
            plan_path = root / 'plan/plan.json'
            plan = json.loads(plan_path.read_text())
            trial = plan['trials'][0]
            receipt = {
                'kind': 'synthetic-receipt',
                'trial_id': trial['id'],
                'taskId': 't',
                'runId': 'r',
                'threadId': 'h',
                'providerInstanceId': 'synthetic',
                'model': 'fixture',
                'options': {},
                'executedModel': 'fixture',
                'status': 'pass',
                'dimensions': {'probe': True},
                'integrity': 'ok',
                'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                'checker_sha256': trial['conditions']['checker_sha256'],
            }
            path = root / 'receipt.json'
            path.write_text(json.dumps(receipt))
            sub = root / 'sub'
            sub.mkdir()
            (sub / 'x').write_text('synthetic')
            results = root / 'results'
            results.mkdir()
            self.assertEqual(self.run_cli('collect', '--plan', plan_path, '--trial-id', trial['id'], '--receipt', path, '--submission', sub, '--out', results / 'one').returncode, 0)
            self.assertEqual(self.run_cli('report', '--plan', plan_path, '--results', results, '--out', root / 'report').returncode, 0)
            row = json.loads((root / 'report/report.json').read_text())['raw_trials'][0]
            self.assertEqual(row['status'], 'skipped')
            self.assertEqual(row['required_checks'], 'missing')

    def test_budget_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'synthetic',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 3,
                'budget': {'producer_runs': 11, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'synthetic', 'model': 'fixture', 'options': {}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
            }
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            out = root / 'out'
            self.assertNotEqual(self.run_cli('plan', '--config', path, '--out', out).returncode, 0)
            self.assertFalse(out.exists())

if __name__ == '__main__':
    unittest.main()
