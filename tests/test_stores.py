"""Store switches and platform order. Run: python -m unittest discover tests"""
import unittest

from desk import stores


class FakeProject:
    def __init__(self, data):
        self.data = data

    def read(self, rel, default=None):
        return self.data if rel == "store.json" else default

    def write(self, rel, data):
        self.data = data


def order(data):
    return [g for g, _ in stores.groups(FakeProject(data))]


class GroupOrder(unittest.TestCase):
    DEFAULT = ["pc", "android", "xr", "console", "apple"]

    def test_default(self):
        self.assertEqual(order({}), self.DEFAULT)
        self.assertEqual(order(None), self.DEFAULT)
        self.assertEqual(stores.groups(None)[0][0], "pc")

    def test_android_first(self):
        self.assertEqual(order({"first": ["android"]}), ["android", "pc", "xr", "console", "apple"])
        self.assertEqual([s[0] for s in stores.desk_order(FakeProject({"first": ["android"]}))][:3], ["itch-android", "play", "samsung"])

    def test_invalid_values_are_ignored(self):
        for bad in (None, 3, "android", [["android"]], [None, 5], {"android": True}, ["nope"]):
            self.assertEqual(order({"first": bad}), self.DEFAULT, bad)

    def test_duplicates_dropped(self):
        self.assertEqual(order({"first": ["android", "android", "xr"]}), ["android", "xr", "pc", "console", "apple"])

    def test_save(self):
        p = FakeProject({"stores": {"steam": False}})
        stores.save(p, {"first": ["android", "android"], "steam": True})
        self.assertEqual(p.data["first"], ["android"])
        self.assertNotIn("steam", p.data["stores"])
        stores.save(p, {"first": "android"})
        self.assertNotIn("first", p.data)
        with self.assertRaises(ValueError):
            stores.save(p, {"bogus": False})


class Switches(unittest.TestCase):
    def test_new_store_is_on(self):
        p = FakeProject({"stores": {"steam": False}})
        self.assertFalse(stores.is_on(p, "steam"))
        self.assertTrue(stores.is_on(p, "itch-android"))
        self.assertEqual(stores.on_kinds(p, ["steam-windows", "itch-windows"]), ["itch-windows"])


if __name__ == "__main__":
    unittest.main()
