from __future__ import annotations

from dataclasses import dataclass
import pickle

from sklearn.svm import SVC, SVR


@dataclass
class SVMConfig:
    task: str = "classification"
    kernel: str = "rbf"
    c: float = 1.0
    gamma: str = "scale"
    epsilon: float = 0.1


def build_model(config: SVMConfig):
    task = config.task.lower()
    if task == "classification":
        return SVC(C=config.c, kernel=config.kernel, gamma=config.gamma)
    if task == "regression":
        return SVR(C=config.c, kernel=config.kernel, gamma=config.gamma, epsilon=config.epsilon)
    raise ValueError(f"Unsupported task: {config.task}")


def train_model(x, y, config: SVMConfig):
    model = build_model(config)
    model.fit(x, y)
    return model


def predict(model, x):
    return model.predict(x)


def save_model(model, path: str):
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_model(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)
