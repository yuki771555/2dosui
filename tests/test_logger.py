import csv
from datetime import datetime
import tempfile
from pathlib import Path
import unittest

from twodosumi.logger import CsvLogger, LogRow


class LoggerTests(unittest.TestCase):
    def test_writes_header_and_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bed.csv"
            with CsvLogger(str(path)) as logger:
                logger.write(LogRow(datetime(2026, 1, 1, 7, 0), 1, 2, 3, "SLEEPING", ""))
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], CsvLogger.header)
            self.assertEqual(rows[1][4], "SLEEPING")


if __name__ == "__main__":
    unittest.main()

