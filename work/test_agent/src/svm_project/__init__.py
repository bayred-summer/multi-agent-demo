"""SVM project package."""

from .model import SVMConfig, load_model, predict, save_model, train_model

__all__ = [
    "SVMConfig",
    "train_model",
    "predict",
    "save_model",
    "load_model",
]
