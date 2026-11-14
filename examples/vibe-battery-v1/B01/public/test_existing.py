import tempfile
import unittest
from pathlib import Path
import tool

class ExistingTests(unittest.TestCase):
    def test_old_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'store.json'
            path.write_bytes((Path(__file__).parent / 'old.json').read_bytes())
            before = path.read_bytes()
            self.assertEqual(tool.load(path)['entries']['old']['title'], 'Existing')
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                tool.register(path, 'old', 'duplicate')
            self.assertEqual(path.read_bytes(), before)
