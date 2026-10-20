import unittest
from decimal import Decimal
from payroll_review.checks import evaluate_row, positive_decimal, validate_headers

ROW = {
    "employee_id": "E001", "store": "North", "contracted_hours": "160",
    "worked_hours": "172", "overtime_hours": "12", "sick_hours": "0",
    "vacation_hours": "0", "hourly_rate": "21.50", "bonus": "100.00",
}


class NumericTests(unittest.TestCase):
    def check(self, **kwargs):
        return evaluate_row({**ROW, **kwargs}, Decimal(20))

    def test_clean(self):
        self.assertEqual(self.check(), [])

    def test_missing_id(self):
        self.assertIn("MISSING_EMPLOYEE_ID", self.check(employee_id=" "))

    def test_missing_store(self):
        self.assertIn("MISSING_STORE", self.check(store=" "))

    def test_invalid_hours(self):
        self.assertIn("INVALID_OVERTIME_HOURS", self.check(overtime_hours="a"))

    def test_invalid_rate(self):
        self.assertIn("INVALID_HOURLY_RATE", self.check(hourly_rate="-10"))

    def test_nan(self):
        self.assertIsNone(positive_decimal("NaN"))

    def test_infinity(self):
        self.assertIsNone(positive_decimal("Infinity"))

    def test_blank(self):
        self.assertIsNone(positive_decimal(""))

    def test_exact_decimal(self):
        self.assertEqual(positive_decimal(" 0.10 "), Decimal("0.10"))

    def test_zero(self):
        self.assertEqual(positive_decimal("0"), Decimal(0))

    def test_high_overtime(self):
        self.assertIn("HIGH_OVERTIME", self.check(overtime_hours="21"))

    def test_equal_threshold(self):
        self.assertNotIn("HIGH_OVERTIME", self.check(overtime_hours="20"))

    def test_excess_overtime(self):
        self.assertIn("OVERTIME_EXCEEDS_WORKED", self.check(worked_hours="10"))

    def test_absurd_month(self):
        self.assertIn("IMPLAUSIBLE_WORKED_HOURS", self.check(worked_hours="745"))
