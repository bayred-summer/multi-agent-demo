from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
from sklearn.datasets import make_classification, make_regression
from sklearn.metrics import accuracy_score, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from svm_project.cli import run
from svm_project.data import load_csv
from svm_project.model import SVMConfig, load_model, predict, save_model, train_model


class TestSVMWorkflow(unittest.TestCase):
    def test_classification_train_predict(self):
        x, y = make_classification(
            n_samples=120,
            n_features=6,
            n_informative=5,
            n_redundant=0,
            random_state=7,
        )
        config = SVMConfig(task="classification", kernel="rbf", c=1.0)
        model = train_model(x, y, config)
        preds = predict(model, x)
        acc = accuracy_score(y, preds)
        self.assertGreater(acc, 0.85)

    def test_regression_train_predict(self):
        x, y = make_regression(
            n_samples=120,
            n_features=5,
            n_informative=5,
            noise=5.0,
            random_state=11,
        )
        config = SVMConfig(task="regression", kernel="linear", c=10.0, epsilon=0.1)
        model = train_model(x, y, config)
        preds = predict(model, x)
        rmse = float(np.sqrt(mean_squared_error(y, preds)))
        self.assertLess(rmse, 10.0)

    def test_save_and_load_model(self):
        x, y = make_classification(
            n_samples=80,
            n_features=4,
            n_informative=3,
            n_redundant=0,
            random_state=3,
        )
        model = train_model(x, y, SVMConfig(task="classification"))

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.pkl"
            save_model(model, str(model_path))
            loaded = load_model(str(model_path))
            np.testing.assert_array_equal(predict(model, x), predict(loaded, x))

    def test_cli_train_and_evaluate(self):
        x, y = make_classification(
            n_samples=100,
            n_features=4,
            n_informative=3,
            n_redundant=0,
            random_state=13,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_path = tmp_path / "data.csv"
            model_path = tmp_path / "model.pkl"
            np.savetxt(data_path, np.column_stack([x, y]), delimiter=",", fmt="%.8f")

            train_stdout = io.StringIO()
            with redirect_stdout(train_stdout):
                run([
                    "train",
                    "--data",
                    str(data_path),
                    "--model",
                    str(model_path),
                    "--task",
                    "classification",
                ])
            train_payload = json.loads(train_stdout.getvalue().strip())
            self.assertEqual(train_payload["metric"], "accuracy")

            eval_stdout = io.StringIO()
            with redirect_stdout(eval_stdout):
                run([
                    "evaluate",
                    "--data",
                    str(data_path),
                    "--model",
                    str(model_path),
                    "--task",
                    "classification",
                ])
            eval_payload = json.loads(eval_stdout.getvalue().strip())
            self.assertEqual(eval_payload["metric"], "accuracy")
            self.assertGreaterEqual(eval_payload["value"], 0.80)

    def test_csv_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "toy.csv"
            np.savetxt(data_path, np.array([[1.0, 2.0, 0.0], [3.0, 4.0, 1.0]]), delimiter=",")
            x, y = load_csv(str(data_path))
            self.assertEqual(x.shape, (2, 2))
            self.assertEqual(y.shape, (2,))


if __name__ == "__main__":
    unittest.main()
