# test-agent-svm

A runnable Python project for Support Vector Machine (SVM) training and prediction.

## Features
- Classification with `SVC`
- Regression with `SVR`
- CSV data loading
- Model save/load with pickle
- CLI for train, predict, evaluate
- Unit tests

## Project structure
- `src/svm_project/model.py`: model config, train/predict, save/load
- `src/svm_project/data.py`: CSV loader
- `src/svm_project/cli.py`: command-line entry
- `tests/test_svm_workflow.py`: unit tests

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

## Data format
CSV file where each row is one sample and the last column is the target by default.

## Train
```bash
python -m svm_project.cli train --data train.csv --model model.pkl --task classification --kernel rbf --c 1.0
```

## Predict
```bash
python -m svm_project.cli predict --data train.csv --model model.pkl --output pred.csv
```

## Evaluate
```bash
python -m svm_project.cli evaluate --data train.csv --model model.pkl --task classification
```

## Run tests
```bash
python -m unittest discover -s tests -v
```
