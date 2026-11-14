import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def list_entries(path):
    return sorted(load(path)['entries'], key=lambda entry: entry['id'])


def format_entry(entry):
    return entry['id'] + ': ' + entry['title']
