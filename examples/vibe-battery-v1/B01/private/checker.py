import importlib.util
import json
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path


def check(public, submission):
    checks = {'output_scope': all(p.is_file() and not p.is_symlink() and p.name in ('tool.py', 'test_note.py') for p in submission.iterdir())}
    commands = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        tool = submission / 'tool.py'
        spec = importlib.util.spec_from_file_location('candidate', tool)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old = (public / 'old.json').read_bytes()
        path = work / 'data.json'
        for name, note in [('default', None), ('empty', ''), ('chinese', '中文'), ('whitespace', '  \t')]:
            path.write_bytes(old)
            cmd = [sys.executable, '-B', str(tool), '--file', str(path), 'register', '--id', 'new', '--title', 'Title']
            if note is not None:
                cmd += ['--note', note]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            commands.append({'argv': cmd, 'exit': proc.returncode, 'stderr': proc.stderr})
            try:
                record = json.loads(path.read_text(encoding='utf-8'))['entries']['new']
                checks[name] = proc.returncode == 0 and (('note' not in record) if note is None else record.get('note') == note)
            except (ValueError, KeyError):
                checks[name] = False
        checks['non_string'] = True
        for value in (None, 0, False, [], {}):
            path.write_bytes(old)
            try:
                module.register(path, 'new', 'Title', note=value)
                rejected = False
            except (TypeError, ValueError):
                rejected = True
            checks['non_string'] &= rejected and path.read_bytes() == old
        path.write_bytes(old)
        try:
            module.register(path, 'bad', 'Title', note='\ud800')
            checks['failed_write'] = False
        except (UnicodeError, ValueError):
            checks['failed_write'] = path.read_bytes() == old
        path.write_bytes(old)
        try:
            module.load(path)
            checks['read_only'] = path.read_bytes() == old
        except Exception:
            checks['read_only'] = False
        cmd = [sys.executable, '-B', str(tool), '--file', str(path), 'list']
        proc = subprocess.run(cmd, capture_output=True, text=True)
        commands.append({'argv': cmd, 'exit': proc.returncode, 'stderr': proc.stderr})
        checks['read_only'] &= proc.returncode == 0 and path.read_bytes() == old
        shutil.copy2(tool, work / 'tool.py')
        shutil.copy2(public / 'test_existing.py', work / 'test_existing.py')
        shutil.copy2(public / 'old.json', work / 'old.json')
        cmd = [sys.executable, '-B', '-m', 'unittest', 'test_existing']
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
        commands.append({'argv': cmd, 'exit': proc.returncode, 'stderr': proc.stderr, 'note': 'public original test'})
        checks['existing'] = proc.returncode == 0
    return {'dimensions': checks, 'commands': commands}
