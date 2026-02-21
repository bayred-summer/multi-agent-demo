from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, mean_squared_error

from .data import load_csv, save_vector
from .model import SVMConfig, load_model, predict, save_model, train_model


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument("--data", required=True, help="CSV data path")
    parser.add_argument("--model", required=True, help="Model file path")
    parser.add_argument("--target-col", type=int, default=-1, help="Target column index")


def cmd_train(args):
    x, y = load_csv(args.data, args.target_col)
    config = SVMConfig(
        task=args.task,
        kernel=args.kernel,
        c=args.c,
        gamma=args.gamma,
        epsilon=args.epsilon,
    )
    model = train_model(x, y, config)
    model_path = Path(args.model)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    save_model(model, str(model_path))

    preds = predict(model, x)
    if args.task == "classification":
        metric = accuracy_score(y, preds)
        payload = {"task": args.task, "metric": "accuracy", "value": float(metric)}
    else:
        rmse = math.sqrt(mean_squared_error(y, preds))
        payload = {"task": args.task, "metric": "rmse", "value": float(rmse)}
    print(json.dumps(payload, ensure_ascii=True))


def cmd_predict(args):
    x, _ = load_csv(args.data, args.target_col)
    model = load_model(args.model)
    preds = predict(model, x)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_vector(str(output_path), preds)
    else:
        print("\n".join(str(v) for v in preds.tolist()))


def cmd_evaluate(args):
    x, y = load_csv(args.data, args.target_col)
    model = load_model(args.model)
    preds = predict(model, x)

    if args.task == "classification":
        metric = accuracy_score(y, preds)
        payload = {"task": args.task, "metric": "accuracy", "value": float(metric)}
    else:
        rmse = math.sqrt(mean_squared_error(y, preds))
        payload = {"task": args.task, "metric": "rmse", "value": float(rmse)}
    print(json.dumps(payload, ensure_ascii=True))


def build_parser():
    parser = argparse.ArgumentParser(description="SVM project CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Train an SVM model")
    _add_common_args(train)
    train.add_argument("--task", choices=["classification", "regression"], default="classification")
    train.add_argument("--kernel", default="rbf")
    train.add_argument("--c", type=float, default=1.0)
    train.add_argument("--gamma", default="scale")
    train.add_argument("--epsilon", type=float, default=0.1)
    train.set_defaults(func=cmd_train)

    predict_cmd = sub.add_parser("predict", help="Run prediction")
    _add_common_args(predict_cmd)
    predict_cmd.add_argument("--output", help="Optional prediction output CSV path")
    predict_cmd.set_defaults(func=cmd_predict)

    evaluate = sub.add_parser("evaluate", help="Evaluate an existing model")
    _add_common_args(evaluate)
    evaluate.add_argument("--task", choices=["classification", "regression"], default="classification")
    evaluate.set_defaults(func=cmd_evaluate)

    return parser


def run(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
