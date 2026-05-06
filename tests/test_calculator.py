import unittest

from simple_project import add


class TestCalculator(unittest.TestCase):
    def test_add_positive_numbers(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_add_negative_numbers(self) -> None:
        self.assertEqual(add(-2, -3), -5)


if __name__ == "__main__":
    unittest.main()
