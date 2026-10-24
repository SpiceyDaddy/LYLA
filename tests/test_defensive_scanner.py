import json
import unittest

from src.defensive_scanner import DefensiveFileScanner


class DefensiveFileScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = DefensiveFileScanner()

    def test_detects_code_risks_and_secrets_without_returning_secret_values(self):
        source = (
            'API_KEY = "a-realistic-secret-value-987654"\n'
            "result = eval(user_input)\n"
            "subprocess.run(command, shell=True)\n"
            "pickle.loads(payload)\n"
            "yaml.load(data)\n"
            "tempfile.mktemp()\n"
            "hashlib.md5(value)\n"
        )
        result = self.scanner.scan("src/example.py", source)

        rules = [finding["rule"] for finding in result["findings"]]
        self.assertEqual(
            rules,
            ["SEC001", "PY001", "PY002", "PY003", "PY004", "PY005", "PY006"],
        )
        self.assertEqual(
            [finding["line"] for finding in result["findings"]],
            list(range(1, 8)),
        )
        self.assertNotIn("a-realistic-secret-value-987654", json.dumps(result))
        self.assertEqual(result["summary"]["by_severity"]["HIGH"], 2)
        self.assertIn("not proof of safety", result["disclaimer"])

    def test_private_key_and_token_findings_do_not_disclose_material(self):
        key_marker = "-----BEGIN PRIVATE KEY-----"
        token = "AKIA1234567890ABCDEF"
        result = self.scanner.scan(
            "config.txt",
            f"{key_marker}\n{token}\n",
        )
        encoded = json.dumps(result)
        self.assertIn("SEC002", encoded)
        self.assertIn("SEC003", encoded)
        self.assertNotIn(token, encoded)

    def test_placeholder_secrets_are_not_reported(self):
        result = self.scanner.scan(
            "settings.py",
            'API_KEY = "your_api_key_here"\n'
            'PASSWORD = "changeme-now"\n'
            'PASSWORD = "latest-weather"\n',
        )
        self.assertEqual(
            [finding["rule"] for finding in result["findings"]],
            ["SEC001"],
        )
        self.assertEqual(result["findings"][0]["line"], 3)

    def test_python_rules_do_not_run_on_other_file_types(self):
        result = self.scanner.scan("notes.txt", "result = eval(user_input)\n")
        self.assertEqual(result["findings"], [])

    def test_ignores_python_comments_for_code_risk_patterns(self):
        result = self.scanner.scan("src/example.py", "# eval(value)\n")
        self.assertEqual(result["findings"], [])

    def test_limits_file_size_and_number_of_findings(self):
        with self.assertRaisesRegex(ValueError, "1 MB"):
            self.scanner.scan("large.py", "x" * 1_048_577)

        source = "\n".join("eval(value)" for _ in range(300))
        result = self.scanner.scan("many.py", source)
        self.assertEqual(result["summary"]["total"], 300)
        self.assertEqual(result["summary"]["shown"], 200)
        self.assertTrue(result["summary"]["truncated"])


if __name__ == "__main__":
    unittest.main()
