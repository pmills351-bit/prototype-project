import os
import numpy as np
import onnxruntime as ort

# === Build a tiny iris model locally on first run (no download needed) ===
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

MODEL = "data/iris.onnx"

def _ensure_model():
    """Create and save an iris classifier as ONNX if it doesn't exist."""
    if os.path.exists(MODEL):
        return
    print("⚙️  Exporting iris model to ONNX...")
    X, y = load_iris(return_X_y=True)
    clf = LogisticRegression(max_iter=200).fit(X, y)

    initial_type = [("float_input", FloatTensorType([None, 4]))]
    onx = convert_sklearn(clf, initial_types=initial_type)

    os.makedirs("data", exist_ok=True)
    with open(MODEL, "wb") as f:
        f.write(onx.SerializeToString())
    print("✅ Model saved:", MODEL)

_ensure_model()

# === Runtime wrapper using DirectML if available ===
class IrisModel:
    def __init__(self, path: str):
        providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        self.sess = ort.InferenceSession(path, providers=providers)
        self.iname = self.sess.get_inputs()[0].name
        self.oname = self.sess.get_outputs()[0].name

    def predict(self, X: np.ndarray):
        X = np.asarray(X, dtype=np.float32)
        return self.sess.run([self.oname], {self.iname: X})[0]

_model = IrisModel(MODEL)

def predict_one(features):
    """features: [sepal_len, sepal_wid, petal_len, petal_wid]"""
    x = np.array([features], dtype=np.float32)
    y = _model.predict(x)          # may be shape (1,) label OR (1, n_classes) probs
    y = np.asarray(y)

    # If model returns a single class label (shape (1,))
    if y.ndim == 1:
        return int(y[0])

    # If model returns class probabilities/logits (shape (1, n_classes))
    if y.ndim == 2 and y.shape[1] > 1:
        return int(np.argmax(y, axis=1)[0])

    # Fallback: flatten and take first
    return int(y.ravel()[0])
