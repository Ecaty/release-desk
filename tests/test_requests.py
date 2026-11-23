"""The desk answers only its own page: right Host, and for POST its own Origin and JSON."""
import unittest

from desk.server import refusal

PORT = 27760
OK = {"Host": "127.0.0.1:27760", "Origin": "http://127.0.0.1:27760", "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"}


class Requests(unittest.TestCase):
    def test_own_page(self):
        self.assertEqual(refusal("POST", OK, PORT), "")
        self.assertEqual(refusal("POST", dict(OK, Host="localhost:27760", Origin="http://localhost:27760"), PORT), "")
        self.assertEqual(refusal("POST", dict(OK, **{"Content-Type": "application/json; charset=utf-8"}), PORT), "")
        self.assertEqual(refusal("GET", {"Host": "127.0.0.1:27760"}, PORT), "")
        # A script on this PC (no browser headers) still works.
        self.assertEqual(refusal("POST", {"Host": "127.0.0.1:27760", "Content-Type": "application/json"}, PORT), "")

    def test_other_pages_refused(self):
        cases = [
            ("GET", {"Host": "evil.example:27760"}),  # DNS rebinding
            ("GET", {}),
            ("POST", dict(OK, Host="evil.example:27760")),
            ("POST", dict(OK, Host="127.0.0.1:8080")),
            ("POST", dict(OK, Origin="https://evil.example")),
            ("POST", dict(OK, Origin="null")),
            ("POST", dict(OK, Origin="http://127.0.0.1:27760.evil.example")),
            ("POST", dict(OK, **{"Sec-Fetch-Site": "cross-site"})),
            ("POST", dict(OK, **{"Sec-Fetch-Site": "same-site"})),
            ("POST", dict(OK, **{"Content-Type": "text/plain"})),  # a no-cors form post
            ("POST", dict(OK, **{"Content-Type": "application/x-www-form-urlencoded"})),
            ("POST", {k: v for k, v in OK.items() if k != "Content-Type"}),
        ]
        for method, headers in cases:
            self.assertTrue(refusal(method, headers, PORT), (method, headers))


if __name__ == "__main__":
    unittest.main()
