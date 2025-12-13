# train_mnist_digit_model.py

import tensorflow as tf
layers = tf.keras.layers
models = tf.keras.models

from pathlib import Path

def build_cnn_model(input_shape=(28, 28, 1)) -> tf.keras.Model:
    model = models.Sequential(
        [
            layers.Conv2D(32, (3, 3), activation="relu", input_shape=input_shape),
            layers.MaxPooling2D((2, 2)),
            layers.Conv2D(64, (3, 3), activation="relu"),
            layers.MaxPooling2D((2, 2)),
            layers.Conv2D(64, (3, 3), activation="relu"),
            layers.Flatten(),
            layers.Dense(128, activation="relu"),
            layers.Dense(10, activation="softmax"),
        ]
    )
    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def main():
    # Load MNIST
    (x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

    # Normalize to [0,1] and add channel dim
    x_train = (x_train.astype("float32") / 255.0)[..., None]
    x_test = (x_test.astype("float32") / 255.0)[..., None]

    model = build_cnn_model()
    model.summary()

    # Train
    model.fit(
        x_train,
        y_train,
        epochs=5,
        batch_size=64,
        validation_split=0.1,
    )

    # Evaluate
    test_loss, test_acc = model.evaluate(x_test, y_test, verbose=2)
    print(f"Test accuracy: {test_acc:.4f}")

    # this script lives at PACKAGE_ROOT/src/package_name/ocr/train_mnist_digit_model.py
    # model data lives at PACKAGE_ROOT/data/models/mnist_digit_cnn.keras
    PACKAGE_ROOT = Path(__file__).parents[2]
    out_path = PACKAGE_ROOT / "data" / "models" / "mnist_digit_cnn.keras"
    model.save(out_path)
    print(f"Saved digit model to {out_path}")


if __name__ == "__main__":
    main()
