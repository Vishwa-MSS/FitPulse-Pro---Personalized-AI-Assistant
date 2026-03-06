"""
train_gaze.py
=============
Train Eye State CNN for Gaze / Focus Detection
Run this ONCE to produce: models/eye_state_cnn_model_finetuned.keras

Dataset layout expected (your existing structure):
  datasets/GAZE/
    data/
      train/   (open/ + closed/  subfolders)
      val/     (open/ + closed/  subfolders)
      test/    (open/ + closed/  subfolders)
    cew-eyes-dataset/
      (alternative: flat folder per class)

Usage:
  cd fitpulse-pro/
  python train_models/train_gaze.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, models
from tensorflow.keras.preprocessing.image import ImageDataGenerator

# ─── CONFIG ──────────────────────────────────────────────────────────────────
# Point to your dataset — adjust if your structure differs
TRAIN_DIR  = os.path.join('datasets', 'GAZE', 'data', 'train')
VAL_DIR    = os.path.join('datasets', 'GAZE', 'data', 'val')
MODEL_OUT  = os.path.join('models', 'eye_state_cnn_model_finetuned.keras')
IMG_SIZE   = (64, 64)
BATCH_SIZE = 32
EPOCHS     = 50

os.makedirs('models', exist_ok=True)

def build_eye_cnn():
    """Binary classifier: 0=OPEN, 1=CLOSED"""
    model = models.Sequential([
        layers.Conv2D(32, (3,3), activation='relu', input_shape=(64,64,1), padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.25),

        layers.Conv2D(64, (3,3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.25),

        layers.Conv2D(128, (3,3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.25),

        layers.Flatten(),
        layers.Dense(256, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.5),
        layers.Dense(1, activation='sigmoid')    # binary output
    ])
    model.compile(
        optimizer=keras.optimizers.Adam(0.001),
        loss='binary_crossentropy',
        metrics=['accuracy', keras.metrics.AUC(name='auc')]
    )
    return model

def main():
    print("="*60)
    print("  FitPulse Pro — Gaze / Eye State Model Training")
    print("="*60)

    if not os.path.isdir(TRAIN_DIR):
        print(f"❌ Training data not found at: {TRAIN_DIR}")
        print("   Ensure your GAZE dataset is in: datasets/GAZE/data/train/")
        print("   With subfolders: open/ and closed/")
        return

    train_gen = ImageDataGenerator(
        rescale=1./255, rotation_range=10,
        width_shift_range=0.1, height_shift_range=0.1,
        zoom_range=0.1, horizontal_flip=True
    ).flow_from_directory(
        TRAIN_DIR, target_size=IMG_SIZE, color_mode='grayscale',
        batch_size=BATCH_SIZE, class_mode='binary', shuffle=True
    )

    val_gen = ImageDataGenerator(rescale=1./255).flow_from_directory(
        VAL_DIR, target_size=IMG_SIZE, color_mode='grayscale',
        batch_size=BATCH_SIZE, class_mode='binary', shuffle=False
    )

    print(f"\nTrain: {train_gen.samples} | Val: {val_gen.samples}")
    print(f"Classes: {train_gen.class_indices}")

    model = build_eye_cnn()
    model.summary()

    callbacks = [
        keras.callbacks.ModelCheckpoint(MODEL_OUT, monitor='val_accuracy',
                                        save_best_only=True, verbose=1),
        keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5,
                                          patience=5, min_lr=1e-7, verbose=1),
        keras.callbacks.EarlyStopping(monitor='val_loss', patience=12,
                                      restore_best_weights=True, verbose=1)
    ]

    model.fit(train_gen, validation_data=val_gen,
              epochs=EPOCHS, callbacks=callbacks, verbose=1)

    print(f"\n✅ Eye model saved: {MODEL_OUT}")


if __name__ == '__main__':
    main()
