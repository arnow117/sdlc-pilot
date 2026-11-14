"""Controlled host contract tests. Stub evidence only; no model or MCP calls."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import vibe_host
import vibe_test as core
ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / 'examples/vibe-battery-v1/battery.json'

class HostContractTests(unittest.TestCase):

    def test_native_aliases_and_options_preserve_unknown_model(self):
        raw = {
            'taskId': 't',
            'childRunId': 'r',
            'childThreadId': 'h',
            'providerInstanceId': 'provider',
            'model': 'requested',
            'options': [{'id': 'effort', 'value': 'xhigh'}],
            'executedModel': None,
            'status': 'completed',
            'startedAt': '2026-11-14T09:42:38.536Z',
            'completedAt': '2026-11-14T09:50:42.491Z',
        }
        result = vibe_host.normalize_native(raw)
        self.assertEqual(result['runId'], 'r')
        self.assertEqual(result['threadId'], 'h')
        self.assertEqual(result['options'], {'effort': 'xhigh'})
        self.assertIsNone(result['executedModel'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['start'], raw['startedAt'])
        self.assertEqual(result['end'], raw['completedAt'])
        self.assertEqual(result['raw'], raw)

    def test_live_prepare_requires_callback_and_counts_pending_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'live',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'provider', 'model': 'model', 'options': {'effort': 'xhigh'}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
                'required_dimensions': {'B01': ['probe'], 'B02': ['probe']},
            }
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            core.plan(path, root / 'plan')
            plan_path = root / 'plan/plan.json'
            plan_data = json.loads(plan_path.read_text())
            plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            trial = plan_data['trials'][0]
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'no-context')

            def verify(stage, facts):
                return {
                    'plan_sha256': plan_sha,
                    'approved': True,
                    'revoked': False,
                    'oracle_battery_sha256': plan_data['battery_sha256'],
                    'oracle_pass': True,
                    'isolated': True,
                    'workspace_verified': True,
                    'access_verified': True,
                    'approved_trials': [item['id'] for item in plan_data['trials']],
                    'approved_judge': True,
                    'oracle_evidence_sha256': 'a' * 64,
                    'isolation_evidence_sha256': 'b' * 64,
                    'workspace_evidence_sha256': 'c' * 64,
                    'access_evidence_sha256': 'd' * 64,
                    'policy_evidence_sha256': 'f' * 64,
                    'requested_target': plan_data['target'],
                    'permissions': plan_data['permissions'],
                    'limits': plan_data['limits'],
                    'limit_enforcement': 'not-enforced-disclosed',
                    'attempts': [],
                }
            host = vibe_host.HostContext(verify)
            self.assertEqual(core.prepare(plan_path, trial['id'], root / 'allowed', host_context=host), 0)

            def pending(stage, facts):
                result = verify(stage, facts)
                result['attempts'] = [{'trial_id': plan_data['trials'][1]['id'], 'taskId': 't', 'childRunId': 'r', 'childThreadId': 'h', 'status': 'unknown'}]
                return result
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'pending', host_context=vibe_host.HostContext(pending))
            self.assertFalse((root / 'pending').exists())

            def unknown_ids(stage, facts):
                result = verify(stage, facts)
                result['attempts'] = [{'trial_id': plan_data['trials'][1]['id'], 'status': 'unknown'}]
                return result
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                core.prepare(plan_path, trial['id'], root / 'unknown-ids', host_context=vibe_host.HostContext(unknown_ids))
            empty_results = root / 'empty-results'
            empty_results.mkdir()
            core.control_handoff(plan_path, empty_results, root / 'pending-handoff',
                                 host_context=vibe_host.HostContext(pending))
            handoff = json.loads((root / 'pending-handoff/handoff.json').read_text())
            self.assertEqual(handoff['used_slots'], 1)
            self.assertEqual(handoff['candidate_cancel_taskIds'], ['t'])
            core.control_handoff(plan_path, empty_results, root / 'unknown-handoff',
                                 host_context=vibe_host.HostContext(unknown_ids))
            handoff = json.loads((root / 'unknown-handoff/handoff.json').read_text())
            self.assertEqual(handoff['used_slots'], 1)
            self.assertEqual(handoff['candidate_cancel_taskIds'], [])
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'raw-json', host_context={'verified': True})

            def revoked(stage, facts):
                result = verify(stage, facts)
                result['revoked'] = True
                return result
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'revoked', host_context=vibe_host.HostContext(revoked))

            def wrong_policy(stage, facts):
                result = verify(stage, facts)
                result['permissions'] = ['unexpected']
                return result
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'wrong-policy',
                             host_context=vibe_host.HostContext(wrong_policy))

            def exhausted(stage, facts):
                result = verify(stage, facts)
                result['attempts'] = [{'trial_id': item['id'], 'taskId': f't{i}', 'childRunId': f'r{i}', 'childThreadId': f'h{i}', 'status': 'completed'} for i, item in enumerate(plan_data['trials'])]
                return result
            with self.assertRaises(ValueError):
                core.prepare(plan_path, trial['id'], root / 'exhausted', host_context=vibe_host.HostContext(exhausted))

            def reused(stage, facts):
                result = exhausted(stage, facts)
                result['attempts'][1]['childThreadId'] = result['attempts'][0]['childThreadId']
                return result
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                core.prepare(plan_path, trial['id'], root / 'reused', host_context=vibe_host.HostContext(reused))

            def reused_run(stage, facts):
                result = exhausted(stage, facts)
                result['attempts'][1]['childRunId'] = result['attempts'][0]['childRunId']
                return result
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                core.prepare(plan_path, trial['id'], root / 'reused-run', host_context=vibe_host.HostContext(reused_run))

    def test_live_scoring_is_bound_to_independent_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            config = {
                'kind': 'live',
                'battery': str(BATTERY),
                'documents': [],
                'repetitions': 1,
                'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                'target': {'providerInstanceId': 'provider', 'model': 'model', 'options': {'effort': 'xhigh'}},
                'permissions': [],
                'limits': {'seconds': 900, 'output_tokens': 24000},
                'approval_status': 'approved',
                'required_dimensions': {'B01': ['probe'], 'B02': ['probe']},
            }
            cfg = root / 'config.json'
            cfg.write_text(json.dumps(config))
            core.plan(cfg, root / 'plan')
            plan_path = root / 'plan/plan.json'
            plan = json.loads(plan_path.read_text())
            plan_sha = core.digest(plan_path)
            trial = plan['trials'][0]
            submission = root / 'submission'
            submission.mkdir()
            (submission / 'output.txt').write_text('example')
            raw = {
                'taskId': 't',
                'childRunId': 'r',
                'childThreadId': 'h',
                'providerInstanceId': 'provider',
                'model': 'model',
                'options': [{'name': 'effort', 'value': 'xhigh'}],
                'executedModel': 'actual',
                'status': 'completed',
                'start': '2026-11-14T00:00:00Z',
                'end': '2026-11-14T00:01:00Z',
            }
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps(raw))
            attempt = {**raw, 'trial_id': trial['id']}

            def verify(stage, facts):
                return {
                    'plan_sha256': plan_sha,
                    'approved': True,
                    'revoked': False,
                    'approved_trials': [item['id'] for item in plan['trials']],
                    'approved_judge': True,
                    'oracle_battery_sha256': plan['battery_sha256'],
                    'oracle_pass': True,
                    'oracle_evidence_sha256': 'a' * 64,
                    'isolated': True,
                    'workspace_verified': True,
                    'access_verified': True,
                    'isolation_evidence_sha256': 'b' * 64,
                    'workspace_evidence_sha256': 'c' * 64,
                    'access_evidence_sha256': 'd' * 64,
                    'policy_evidence_sha256': 'f' * 64,
                    'requested_target': plan['target'],
                    'permissions': plan['permissions'],
                    'limits': plan['limits'],
                    'limit_enforcement': 'not-enforced-disclosed',
                    'attempts': [attempt],
                    'native_receipt_sha256': facts.get('native_receipt_sha256'),
                    'scorer': {
                        'independent': True,
                        'isolated': True,
                        'plan_sha256': plan_sha,
                        'trial_id': trial['id'],
                        'checker_sha256': trial['conditions']['checker_sha256'],
                        'submission_tree_sha256': facts.get('submission_tree_sha256'),
                        'status': 'fail',
                        'dimensions': {'probe': False},
                        'integrity': 'ok',
                        'evidence_sha256': 'e' * 64,
                        'sessionId': 'independent-scorer',
                        'evidence_ref': 'stub://scorer',
                    },
                }
            with self.assertRaises(ValueError):
                core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'blocked')
            self.assertEqual(core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'result', host_context=vibe_host.HostContext(verify)), 0)
            saved = json.loads((root / 'result/result.json').read_text())
            self.assertEqual(saved['normalized_receipt']['status'], 'completed')
            self.assertEqual(saved['host_score']['status'], 'fail')

            def wrong_plan(stage, facts):
                result = verify(stage, facts)
                result['plan_sha256'] = '0' * 64
                return result
            with self.assertRaises(ValueError):
                core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'wrong-plan', host_context=vibe_host.HostContext(wrong_plan))

            def unbound_scorer(stage, facts):
                result = verify(stage, facts)
                result['scorer'].pop('checker_sha256')
                return result
            with self.assertRaises(ValueError):
                core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'unbound', host_context=vibe_host.HostContext(unbound_scorer))

            def reused_scorer(stage, facts):
                result = verify(stage, facts)
                result['scorer']['sessionId'] = 'h'
                return result
            with self.assertRaises(ValueError):
                core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'same-scorer',
                                   host_context=vibe_host.HostContext(reused_scorer))
            bad = dict(raw, executedModel=None)
            receipt.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                core.collect_trial(plan_path, trial['id'], receipt, submission, root / 'unknown', host_context=vibe_host.HostContext(verify))

    def test_stub_host_full_live_contract_and_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            contexts = {}

            def verify(stage, facts):
                state = contexts[facts['plan_sha256']]
                result = {
                    'plan_sha256': facts['plan_sha256'],
                    'approved': True,
                    'revoked': False,
                    'approved_trials': [t['id'] for t in state['plan']['trials']],
                    'approved_judge': True,
                    'oracle_battery_sha256': state['plan']['battery_sha256'],
                    'oracle_pass': True,
                    'oracle_evidence_sha256': 'a' * 64,
                    'isolated': True,
                    'workspace_verified': True,
                    'access_verified': True,
                    'isolation_evidence_sha256': 'b' * 64,
                    'workspace_evidence_sha256': 'c' * 64,
                    'access_evidence_sha256': 'd' * 64,
                    'policy_evidence_sha256': 'f' * 64,
                    'requested_target': state['plan']['target'],
                    'permissions': state['plan']['permissions'],
                    'limits': state['plan']['limits'],
                    'limit_enforcement': 'not-enforced-disclosed',
                    'attempts': state['attempts'],
                }
                if stage == 'collect':
                    expected = state['scores'][facts['trial_id']]
                    result['native_receipt_sha256'] = expected['receipt_sha256']
                    result['scorer'] = expected['score']
                if stage == 'judge_collect':
                    result.update(judge_independent=True, judge_payload_sha256=state['judge_payload'], native_receipt_sha256=state['judge_receipt'], ratings_sha256=state['ratings_sha'], judge_target={'providerInstanceId': 'judge-provider', 'model': 'judge-model', 'options': {}})
                if stage == 'compare':
                    result.update(report_sha256=state.get('report_sha256'), report_complete=True)
                return result
            host = vibe_host.HostContext(verify)
            paths = []
            for batch in ('before', 'after'):
                folder = root / batch
                folder.mkdir()
                doc = folder / 'doc.txt'
                doc.write_text('old' if batch == 'before' else 'new')
                config = {
                    'kind': 'live',
                    'battery': str(BATTERY),
                    'documents': [str(doc)],
                    'repetitions': 1,
                    'budget': {'producer_runs': 4, 'judge_runs': 1, 'concurrency': 1},
                    'target': {'providerInstanceId': 'provider', 'model': 'model', 'options': {'effort': 'xhigh'}},
                    'permissions': ['read'],
                    'limits': {'seconds': 900, 'output_tokens': 24000},
                    'approval_status': 'approved',
                    'required_dimensions': {'B01': ['probe'], 'B02': ['probe']},
                }
                cfg = folder / 'config.json'
                cfg.write_text(json.dumps(config))
                core.plan(cfg, folder / 'plan')
                plan_path = folder / 'plan/plan.json'
                plan = json.loads(plan_path.read_text())
                plan_sha = core.digest(plan_path)
                state = {'plan': plan, 'attempts': [], 'scores': {}}
                contexts[plan_sha] = state
                results = folder / 'results'
                results.mkdir()
                for index, trial in enumerate(plan['trials']):
                    core.prepare(plan_path, trial['id'], folder / f'prepared-{index}', host_context=host)
                    submission = folder / f'submission-{index}'
                    submission.mkdir()
                    (submission / 'result.txt').write_text('example')
                    native = {
                        'taskId': f't{index}',
                        'childRunId': f'r{index}',
                        'childThreadId': f'h{index}',
                        'providerInstanceId': 'provider',
                        'model': 'model',
                        'options': [{'name': 'effort', 'value': 'xhigh'}],
                        'executedModel': 'actual',
                        'status': 'completed',
                        'start': '2026-11-14T00:00:00Z',
                        'end': '2026-11-14T00:01:00Z',
                    }
                    receipt = folder / f'receipt-{index}.json'
                    receipt.write_text(json.dumps(native))
                    state['attempts'].append({**native, 'trial_id': trial['id']})
                    status = 'fail' if index == 0 else 'timeout' if index == 1 else 'pass'
                    score = {
                        'independent': True,
                        'isolated': True,
                        'plan_sha256': plan_sha,
                        'trial_id': trial['id'],
                        'checker_sha256': trial['conditions']['checker_sha256'],
                        'submission_tree_sha256': core.snapshot_hash(core.checked_tree(submission)),
                        'status': status,
                        'dimensions': {'probe': status == 'pass'},
                        'integrity': 'ok',
                        'evidence_sha256': 'e' * 64,
                        'sessionId': 'independent-scorer',
                        'evidence_ref': 'stub://scorer',
                    }
                    state['scores'][trial['id']] = {'receipt_sha256': core.digest(receipt), 'score': score}
                    core.collect_trial(plan_path, trial['id'], receipt, submission, results / f'{index}', host_context=host)
                core.judge_prepare(plan_path, results, folder / 'judge', host_context=host)
                payload = folder / 'judge/payload.json'
                state['judge_payload'] = core.digest(payload)
                cases = json.loads(payload.read_text())['cases']
                self.assertFalse(any(('control' in json.dumps(case).lower() or 'treatment' in json.dumps(case).lower() for case in cases)))
                judge = {
                    'taskId': 'jt',
                    'childRunId': 'jr',
                    'childThreadId': 'jh',
                    'role': 'judge',
                    'providerInstanceId': 'judge-provider',
                    'model': 'judge-model',
                    'options': [],
                    'executedModel': 'judge-actual',
                    'status': 'completed',
                    'start': '2026-11-14T00:02:00Z',
                    'end': '2026-11-14T00:03:00Z',
                }
                state['attempts'].append(judge)
                judge_receipt = folder / 'judge-receipt.json'
                judge_receipt.write_text(json.dumps(judge))
                state['judge_receipt'] = core.digest(judge_receipt)
                ratings = {'kind': 'host-judge-result', 'ratings': [{'id': case['id'], 'correctness': 2, 'readability': 2, 'protocol': 2, 'evidence': 'result.txt:1'} for case in cases]}
                ratings_path = folder / 'ratings.json'
                ratings_path.write_text(json.dumps(ratings))
                state['ratings_sha'] = core.digest(ratings_path)
                state['judge_payload'] = '0' * 64
                with self.assertRaises(ValueError):
                    core.judge_collect(payload, ratings_path, folder / 'wrong-input', host_context=host, plan_path=plan_path, native_receipt_path=judge_receipt)
                state['judge_payload'] = core.digest(payload)
                state['attempts'][-1]['childThreadId'] = 'h0'
                with self.assertRaises(ValueError):
                    core.judge_collect(payload, ratings_path, folder / 'reused-judge', host_context=host, plan_path=plan_path, native_receipt_path=judge_receipt)
                state['attempts'][-1]['childThreadId'] = 'jh'
                core.judge_collect(payload, ratings_path, folder / 'judged', host_context=host, plan_path=plan_path, native_receipt_path=judge_receipt)
                stored_ratings = folder / 'judged/ratings.json'
                original_ratings = stored_ratings.read_bytes()
                stored_ratings.write_text('{}')
                with self.assertRaises(ValueError):
                    core.report_plan(plan_path, results, folder / 'bad-ratings-report', True,
                                     folder / 'judged/judge-result.json', folder / 'judge/private-map.json',
                                     payload, host_context=host)
                stored_ratings.write_bytes(original_ratings)
                original_map = json.loads((folder / 'judge/private-map.json').read_text())
                blind_ids = list(original_map)
                original_map[blind_ids[0]], original_map[blind_ids[1]] = (
                    original_map[blind_ids[1]], original_map[blind_ids[0]]
                )
                bad_map = folder / 'bad-map.json'
                bad_map.write_text(json.dumps(original_map))
                with self.assertRaisesRegex(ValueError, 'mapping'):
                    core.report_plan(plan_path, results, folder / 'bad-map-report', True,
                                     folder / 'judged/judge-result.json', bad_map, payload,
                                     host_context=host)
                report = folder / 'report'
                result = core.report_plan(plan_path, results, report, True, folder / 'judged/judge-result.json', folder / 'judge/private-map.json', payload, host_context=host)
                self.assertEqual(result, 0)
                data = json.loads((report / 'report.json').read_text())
                self.assertTrue(data['live_complete'])
                self.assertIsNone(data['model_runs'])
                self.assertEqual(data['native_submitted_attempts'], {'producer': 4, 'judge': 1})
                self.assertTrue(any((row['status'] == 'fail' and row['judge_scores']['correctness'] == 2 for row in data['raw_trials'])))
                self.assertTrue(any((row['status'] == 'timeout' for row in data['raw_trials'])))
                timeout_trial = plan['trials'][1]
                timeout_task = next(item for item in data['results'] if item['task'] == timeout_trial['task'])
                timeout_arm = timeout_task['arms'][timeout_trial['arm']]
                self.assertEqual((timeout_arm['quality_denominator'], timeout_arm['pass']), (1, 0))
                state['report_sha256'] = core.digest(report / 'report.json')
                if batch == 'before':
                    severe_results = folder / 'severe-results'
                    import shutil
                    shutil.copytree(results, severe_results)
                    first = plan['trials'][0]['id']
                    state['scores'][first]['score']['integrity'] = 'violation'
                    record_path = severe_results / '0/result.json'
                    record = json.loads(record_path.read_text())
                    record['host_score']['integrity'] = 'violation'
                    record_path.write_text(json.dumps(record))
                    severe = folder / 'severe-report'
                    self.assertEqual(core.report_plan(plan_path, severe_results, severe, True, host_context=host), 1)
                    severe_report = json.loads((severe / 'report.json').read_text())
                    self.assertTrue(all((item['comparison_stopped'] for item in severe_report['results'])))
                    state['scores'][first]['score']['integrity'] = 'ok'
                    facility_results = folder / 'facility-results'
                    shutil.copytree(results, facility_results)
                    state['scores'][first]['score']['status'] = 'facility_failure'
                    facility_record = facility_results / '0/result.json'
                    changed = json.loads(facility_record.read_text())
                    changed['host_score']['status'] = 'facility_failure'
                    facility_record.write_text(json.dumps(changed))
                    facility_report = folder / 'facility-report'
                    self.assertEqual(core.report_plan(plan_path, facility_results, facility_report, True,
                                                      host_context=host), 1)
                    incomplete = json.loads((facility_report / 'report.json').read_text())
                    first_task = next(item for item in incomplete['results'] if item['task'] == plan['trials'][0]['task'])
                    first_arm = first_task['arms'][plan['trials'][0]['arm']]
                    self.assertEqual(first_arm['quality_denominator'], 0)
                    self.assertEqual(first_arm['gaps'][0]['status'], 'facility_failure')
                    state['scores'][first]['score']['status'] = 'fail'
                paths.append(report)
            (root / 'before/doc.txt').write_text('source changed after frozen plan')
            self.assertEqual(core.compare(paths[0], paths[1], root / 'comparison', True, host_context=host), 0)
            comparison = json.loads((root / 'comparison/compare.json').read_text())
            self.assertTrue(comparison['live_attribution'])
            self.assertEqual(core.compare(paths[0], paths[1], root / 'untrusted-comparison', True), 1)
            after_path = paths[1] / 'report.json'
            original = after_path.read_bytes()
            after_data = json.loads(original)
            after_plan = after_data['plan_sha256']
            for field in ('checker', 'model'):
                changed = json.loads(original)
                if field == 'checker':
                    changed['conditions']['tasks'][0]['checker_sha256'] = '0' * 64
                else:
                    changed['actual_routes'][0]['executedModel'] = 'different-model'
                after_path.write_text(json.dumps(changed))
                contexts[after_plan]['report_sha256'] = core.digest(after_path)
                if field == 'checker':
                    with self.assertRaises(ValueError):
                        core.compare(paths[0], paths[1], root / f'changed-{field}', True, host_context=host)
                else:
                    self.assertEqual(core.compare(paths[0], paths[1], root / f'changed-{field}', True, host_context=host), 1)
                    changed_result = json.loads((root / f'changed-{field}' / 'compare.json').read_text())
                    self.assertFalse(changed_result['live_attribution'])
            after_path.write_bytes(original)
            contexts[after_plan]['report_sha256'] = core.digest(after_path)
            self.assertEqual(core.compare(root / 'missing', paths[1], root / 'missing-before', True, host_context=host), 1)
if __name__ == '__main__':
    unittest.main()
