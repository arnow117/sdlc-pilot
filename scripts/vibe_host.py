"""Host-supplied verification callbacks; no MCP, model or authentication calls.

The caller is responsible for authenticating the evidence returned by its callback.
This module validates bindings and does not treat object construction as proof.
"""
from copy import deepcopy
import re


def normalize_options(value):
    if isinstance(value, dict):
        return deepcopy(value)
    if not isinstance(value, list):
        return None
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('invalid native option')
        name = item.get('name', item.get('key', item.get('id')))
        if not isinstance(name, str) or not name or name in result or 'value' not in item:
            raise ValueError('invalid or duplicate native option')
        result[name] = deepcopy(item['value'])
    return result


def normalize_native(raw):
    if not isinstance(raw, dict):
        raise ValueError('native record must be an object')
    aliases = (('childRunId', 'runId'), ('childThreadId', 'threadId'))
    ids = {}
    for primary, alias in aliases:
        if raw.get(primary) and raw.get(alias) and raw[primary] != raw[alias]:
            raise ValueError('conflicting native identifiers')
        ids[alias] = raw.get(primary) or raw.get(alias)
    return {
        'taskId': raw.get('taskId'), 'runId': ids['runId'], 'threadId': ids['threadId'],
        'providerInstanceId': raw.get('providerInstanceId'), 'model': raw.get('model'),
        'options': normalize_options(raw.get('options')), 'executedModel': raw.get('executedModel'),
        'status': raw.get('status'), 'start': raw.get('start', raw.get('startedAt')),
        'end': raw.get('end', raw.get('endedAt', raw.get('completedAt'))),
        'raw': deepcopy(raw),
    }


class HostContext:
    """In-process adapter to a caller-owned evidence verifier, never a JSON credential."""

    def __init__(self, verifier):
        if not callable(verifier):
            raise TypeError('a host verifier callback is required')
        self._verifier = verifier

    def attest(self, stage, facts):
        result = self._verifier(stage, deepcopy(facts))
        if not isinstance(result, dict):
            raise ValueError('host evidence missing')
        if result.get('plan_sha256') != facts.get('plan_sha256'):
            raise ValueError('host evidence plan mismatch')
        return result


def common_evidence(host, stage, plan_sha, plan, facts):
    if not isinstance(host, HostContext):
        raise ValueError('ENV_BLOCKED: controlled host callback required')
    request = {'plan_sha256': plan_sha, **facts}
    evidence = host.attest(stage, request)
    trial_ids = {trial['id'] for trial in plan['trials']}
    approvals = evidence.get('approved_trials')
    if (evidence.get('approved') is not True or evidence.get('revoked') is not False
            or not isinstance(approvals, list) or set(approvals) != trial_ids
            or evidence.get('approved_judge') is not True):
        raise ValueError('approval missing, revoked or wrong scope')
    if (evidence.get('oracle_pass') is not True
            or evidence.get('oracle_battery_sha256') != plan['battery_sha256']
            or not isinstance(evidence.get('oracle_evidence_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', evidence['oracle_evidence_sha256'])):
        raise ValueError('oracle evidence missing or mismatched')
    if not all(evidence.get(key) is True for key in ('isolated', 'workspace_verified', 'access_verified')):
        raise ValueError('host isolation or access evidence missing')
    if (evidence.get('requested_target') != plan['target']
            or evidence.get('permissions') != plan['permissions']
            or evidence.get('limits') != plan['limits']
            or evidence.get('limit_enforcement') not in ('enforced', 'not-enforced-disclosed')):
        raise ValueError('host route, permissions or limit policy mismatch')
    for key in ('isolation_evidence_sha256', 'workspace_evidence_sha256',
                'access_evidence_sha256', 'policy_evidence_sha256'):
        if not isinstance(evidence.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', evidence[key]):
            raise ValueError(f'host evidence digest missing: {key}')
    attempts = evidence.get('attempts')
    if not isinstance(attempts, list):
        raise ValueError('native submission ledger missing')
    producer = []
    judges = []
    seen_tasks, seen_runs, seen_threads, seen_trials = set(), set(), set(), set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError('invalid native attempt')
        native = normalize_native(attempt)
        identifiers = (native['taskId'], native['runId'], native['threadId'])
        if any(value is not None and (not isinstance(value, str) or not value) for value in identifiers):
            raise ValueError('invalid native attempt identifier')
        terminal = attempt.get('status') in ('completed', 'failed', 'cancelled', 'timeout')
        if terminal and not all(identifiers):
            raise ValueError('terminal native attempt identifiers missing')
        if any(value is not None and value in seen
               for value, seen in zip(identifiers, (seen_tasks, seen_runs, seen_threads))):
            raise ValueError('duplicate native task/run/session')
        for value, seen in zip(identifiers, (seen_tasks, seen_runs, seen_threads)):
            if value is not None:
                seen.add(value)
        if attempt.get('role') == 'judge':
            judges.append(attempt)
        else:
            trial_id = attempt.get('trial_id')
            if trial_id not in trial_ids or trial_id in seen_trials:
                raise ValueError('duplicate or unknown trial submission')
            seen_trials.add(trial_id)
            producer.append(attempt)
    if len(producer) > plan['budget']['producer_runs'] or len(judges) > plan['budget']['judge_runs']:
        raise ValueError('native submission budget exceeded')
    return evidence, producer, judges


def allow_prepare(host, plan_sha, plan, trial):
    evidence, attempts, judges = common_evidence(host, 'prepare', plan_sha, plan, {'trial_id': trial['id']})
    if judges:
        raise ValueError('judge already submitted; producer batch closed')
    if len(attempts) >= plan['budget']['producer_runs']:
        raise ValueError('producer budget exhausted')
    if any(item.get('trial_id') == trial['id'] for item in attempts):
        raise ValueError('trial already submitted; retry not allowed')
    if any(item.get('status') not in ('completed', 'failed', 'cancelled', 'timeout') for item in attempts):
        raise ValueError('unresolved native attempt blocks concurrency')
    return evidence


def verify_scored(host, plan_sha, plan, trial, raw, receipt_sha, submission_sha):
    facts = {'trial_id': trial['id'], 'native_receipt_sha256': receipt_sha,
             'submission_tree_sha256': submission_sha,
             'checker_sha256': trial['conditions']['checker_sha256']}
    evidence, attempts, _ = common_evidence(host, 'collect', plan_sha, plan, facts)
    native = normalize_native(raw)
    if not all(isinstance(native.get(key), str) and native[key]
               for key in ('taskId', 'runId', 'threadId', 'providerInstanceId', 'model', 'executedModel')):
        raise ValueError('actual native identity or route unknown')
    if native['options'] is None:
        raise ValueError('actual native options unknown')
    target = trial['conditions']['target']
    if any(native[key] != target[key] for key in ('providerInstanceId', 'model', 'options')):
        raise ValueError('actual native route differs from request')
    matches = [normalize_native(item) for item in attempts if item.get('trial_id') == trial['id']]
    if len(matches) != 1 or any(matches[0][key] != native[key] for key in ('taskId', 'runId', 'threadId', 'status')):
        raise ValueError('receipt does not match submitted native attempt')
    if native['status'] not in ('completed', 'failed', 'timeout'):
        raise ValueError('native execution is not terminal')
    if not all(isinstance(native.get(key), str) and native[key] for key in ('start', 'end')):
        raise ValueError('native start or end time unknown')
    if evidence.get('native_receipt_sha256') != receipt_sha:
        raise ValueError('native receipt is not independently bound')
    score = evidence.get('scorer')
    if not isinstance(score, dict) or score.get('independent') is not True or score.get('isolated') is not True:
        raise ValueError('independent isolated scorer evidence required')
    for key, expected in (('plan_sha256', plan_sha), ('trial_id', trial['id']),
                          ('checker_sha256', trial['conditions']['checker_sha256']),
                          ('submission_tree_sha256', submission_sha)):
        if score.get(key) != expected:
            raise ValueError(f'scorer binding mismatch: {key}')
    if score.get('status') not in ('pass', 'fail', 'timeout', 'skipped', 'facility_failure'):
        raise ValueError('invalid scorer outcome')
    if native['status'] in ('failed', 'timeout') and score['status'] == 'pass':
        raise ValueError('failed native run cannot be a quality pass')
    if not isinstance(score.get('evidence_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', score['evidence_sha256']):
        raise ValueError('scorer evidence digest missing')
    scorer_session = score.get('sessionId')
    if not isinstance(scorer_session, str) or not scorer_session:
        raise ValueError('independent scorer session missing')
    if scorer_session in {normalize_native(item)['threadId'] for item in evidence['attempts']}:
        raise ValueError('scorer session is not independent')
    if not isinstance(score.get('evidence_ref'), str) or not score['evidence_ref']:
        raise ValueError('scorer evidence reference missing')
    if score.get('integrity') not in ('ok', 'violation', 'unknown'):
        raise ValueError('invalid scorer integrity')
    return native, deepcopy(score)


def allow_judge_prepare(host, plan_sha, plan):
    evidence, attempts, judges = common_evidence(host, 'judge_prepare', plan_sha, plan, {})
    if judges:
        raise ValueError('judge already submitted; retry not allowed')
    if any(item.get('status') not in ('completed', 'failed', 'cancelled', 'timeout') for item in attempts):
        raise ValueError('unresolved producer blocks judge concurrency')
    return evidence


def verify_judge(host, plan_sha, plan, payload_sha, raw, receipt_sha, ratings_sha):
    facts = {'judge_payload_sha256': payload_sha, 'native_receipt_sha256': receipt_sha,
             'ratings_sha256': ratings_sha}
    evidence, _, judges = common_evidence(host, 'judge_collect', plan_sha, plan, facts)
    native = normalize_native(raw)
    if not all(isinstance(native.get(key), str) and native[key]
               for key in ('taskId', 'runId', 'threadId', 'providerInstanceId', 'model', 'executedModel')):
        raise ValueError('judge native identity or route unknown')
    if native['options'] is None or native['status'] != 'completed':
        raise ValueError('judge route or completion unknown')
    if not all(isinstance(native.get(key), str) and native[key] for key in ('start', 'end')):
        raise ValueError('judge start or end time unknown')
    if len(judges) != 1:
        raise ValueError('exactly one judge submission is required')
    expected = normalize_native(judges[0])
    if any(expected[key] != native[key] for key in ('taskId', 'runId', 'threadId')):
        raise ValueError('judge receipt does not match submission')
    target = evidence.get('judge_target')
    if not isinstance(target, dict) or any(native[key] != target.get(key)
                                            for key in ('providerInstanceId', 'model', 'options')):
        raise ValueError('judge actual route mismatch')
    if (evidence.get('judge_independent') is not True
            or evidence.get('judge_payload_sha256') != payload_sha
            or evidence.get('native_receipt_sha256') != receipt_sha
            or evidence.get('ratings_sha256') != ratings_sha):
        raise ValueError('independent judge input or receipt evidence missing')
    return native
