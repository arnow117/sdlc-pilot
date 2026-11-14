import json
from pathlib import Path


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    Path(path).write_text(json.dumps(data), encoding='utf-8')
    return data


def list_entries(path):
    return load(path)['entries']


def format_entry(entry):
    return entry['id'] + ' — ' + entry['title']
