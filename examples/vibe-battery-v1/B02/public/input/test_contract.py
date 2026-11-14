import unittest
import current

class PublicContract(unittest.TestCase):
    def test_format_authorized(self):
        self.assertEqual(current.format_entry({'id': 'a', 'title': 'A'}), 'a — A')
