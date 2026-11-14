import ast
import importlib.util
import json
import tempfile
from pathlib import Path


FINDING_FIELDS = {
    'file', 'symbol', 'line_start', 'line_end', 'category',
    'impact', 'suggestion', 'observation',
}
CATEGORIES = {'unexpected_write', 'ordering', 'other'}


def normalize_change(value):
    if type(value) is bool:
        return value
    if value == 'changed':
        return True
    if value == 'unchanged':
        return False
    raise ValueError('invalid byte-change observation')


def is_id_sequence(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def valid_observation(category, observation):
    if not isinstance(observation, dict) or set(observation) != {'expected', 'actual'}:
        return False
    expected = observation['expected']
    actual = observation['actual']
    if category in ('unexpected_write', 'other'):
        try:
            normalize_change(expected)
            normalize_change(actual)
            return True
        except ValueError:
            pass
    if category in ('ordering', 'other'):
        return is_id_sequence(expected) and is_id_sequence(actual)
    return False


def valid_finding(finding):
    if not isinstance(finding, dict) or set(finding) != FINDING_FIELDS:
        return False
    text_fields = ('file', 'symbol', 'category', 'impact', 'suggestion')
    if not all(isinstance(finding[field], str) and finding[field].strip() for field in text_fields):
        return False
    if finding['category'] not in CATEGORIES:
        return False
    start, end = finding['line_start'], finding['line_end']
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        return False
    return valid_observation(finding['category'], finding['observation'])


def probe(public):
    inp = public / 'input'
    source_path = inp / 'current.py'
    source = source_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    locations = {
        node.name: (node.lineno, node.end_lineno)
        for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    spec = importlib.util.spec_from_file_location('current', source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'sample.json'
        path.write_bytes((inp / 'sample.json').read_bytes())
        before = path.read_bytes()
        module.load(path)
        changed = path.read_bytes() != before
        path.write_bytes(before)
        actual = [item['id'] for item in module.list_entries(path)]
    return locations, changed, actual


def matches_location(finding, symbol, line, locations):
    bounds = locations.get(symbol)
    if not bounds:
        return False
    start, end = finding['line_start'], finding['line_end']
    return (
        finding['file'] == 'input/current.py'
        and finding['symbol'] == symbol
        and bounds[0] <= start <= line <= end <= bounds[1]
    )


def matches_write(finding, locations, changed):
    if finding['category'] != 'unexpected_write':
        return False
    if not matches_location(finding, 'load', 7, locations):
        return False
    observation = finding['observation']
    return (
        normalize_change(observation['expected']) is False
        and normalize_change(observation['actual']) is changed
    )


def matches_order(finding, locations, actual):
    if finding['category'] != 'ordering':
        return False
    if not matches_location(finding, 'list_entries', 12, locations):
        return False
    observation = finding['observation']
    return observation['expected'] == sorted(actual) and observation['actual'] == actual


def check(public, submission):
    locations, changed, actual = probe(public)
    findings = json.loads((submission / 'findings.json').read_text(encoding='utf-8'))
    if not isinstance(findings, list):
        raise ValueError('findings must be an array')
    valid = all(valid_finding(finding) for finding in findings)
    write_matches = []
    order_matches = []
    if valid:
        write_matches = [matches_write(finding, locations, changed) for finding in findings]
        order_matches = [matches_order(finding, locations, actual) for finding in findings]
    checks = {
        'schema': valid,
        'write': valid and changed and any(write_matches),
        'ordering': valid and actual != sorted(actual) and any(order_matches),
        'no_false_positive': valid and all(
            write or order for write, order in zip(write_matches, order_matches)
        ),
        'output_scope': (
            sorted(path.name for path in submission.iterdir()) == ['findings.json']
            and not (submission / 'findings.json').is_symlink()
        ),
    }
    return {'dimensions': checks, 'commands': [], 'probe': {'bytes_changed': changed, 'actual_order': actual}}
