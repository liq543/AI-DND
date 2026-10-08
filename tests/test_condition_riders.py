"""A spell condition's rider in the SRD text comes along with it: Hypnotic Pattern's Charmed creature is also Incapacitated."""
import unittest

from engine import srd


class ConditionRiderTest(unittest.TestCase):
    def test_hypnotic_pattern_charm_incapacitates(self):
        fx = srd.data()["spells"]["hypnotic-pattern"]["effect"]
        self.assertEqual(fx["condition"], "charmed")
        self.assertEqual(fx.get("riders"), ["incapacitated"])

    def test_plain_condition_has_no_rider(self):
        self.assertFalse(srd.data()["spells"]["hold-person"]["effect"].get("riders"))


if __name__ == "__main__":
    unittest.main()
