import argparse
import json
import os
import tempfile
from pathlib import Path


def validate_store(value):
    if not isinstance(value, dict) or set(value) != {'entries'} or not isinstance(value['entries'], dict):
        raise ValueError('invalid store')
    for key, entry in value['entries'].items():
        if not isinstance(entry, dict) or set(entry) != {'id', 'title'} or entry['id'] != key:
            raise ValueError('invalid entry')
        if not all(isinstance(entry[field], str) and entry[field] for field in ('id', 'title')):
            raise ValueError('invalid field')
    return value


def load(path):
    return validate_store(json.loads(Path(path).read_text(encoding='utf-8')))


def save(path, store):
    checked = validate_store(store)
    encoded = (json.dumps(checked, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    destination = Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.entry-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encoded)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def register(path, entry_id, title):
    store = load(path)
    if entry_id in store['entries']:
        raise ValueError('duplicate id')
    store['entries'][entry_id] = {'id': entry_id, 'title': title}
    save(path, store)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('register')
    add.add_argument('--id', required=True)
    add.add_argument('--title', required=True)
    commands.add_parser('list')
    args = parser.parse_args()
    if args.command == 'register':
        register(args.file, args.id, args.title)
    else:
        print(json.dumps(load(args.file), ensure_ascii=False))


if __name__ == '__main__':
    main()
