import tempfile
import unittest
from pathlib import Path
import tool

class NoteTests(unittest.TestCase):
    def test_round_trip_and_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.json'
            path.write_text('{"entries": {}}', encoding='utf-8')
            tool.register(path, 'a', 'Title', note=' 中文 ')
            self.assertEqual(tool.load(path)['entries']['a']['note'], ' 中文 ')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                tool.register(path, 'b', 'Title', note=None)
            self.assertEqual(path.read_bytes(), before)
