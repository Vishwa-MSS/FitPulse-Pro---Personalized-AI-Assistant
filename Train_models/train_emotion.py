"""
train_emotion.py
================
Train FER2013 Emotion Recognition CNN
Run this ONCE to produce: models/emotion_model.h5

Dataset layout expected:
  datasets/emotion_recognition/fer2013/
    train/
      angry/     disgust/    fear/
      happy/     neutral/    sad/      surprise/
    test/
      (same 7 subfolders)

Usage:
  cd fitpulse-pro/
  python train_models/train_emotion.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, models
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import numpy as np

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TRAIN_DIR  = os.path.join('datasets', 'emotion_recognition', 'fer2013', 'train')
VAL_DIR    = os.path.join('datasets', 'emotion_recognition', 'fer2013', 'test')
MODEL_OUT  = os.path.join('models', 'emotion_model.h5')
BATCH_SIZE = 64
EPOCHS     = 80
IMG_SIZE   = (48, 48)

os.makedirs('models', exist_ok=True)

def build_model():
    model = models.Sequential([
        # Block 1
        layers.Conv2D(64, (3,3), padding='same', input_shape=(48,48,1)),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.Conv2D(64, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.MaxPooling2D(2,2), layers.Dropout(0.25),

        # Block 2
        layers.Conv2D(128, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.Conv2D(128, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.MaxPooling2D(2,2), layers.Dropout(0.25),

        # Block 3
        layers.Conv2D(256, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.Conv2D(256, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.MaxPooling2D(2,2), layers.Dropout(0.25),

        # Block 4
        layers.Conv2D(512, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.Conv2D(512, (3,3), padding='same'),
        layers.BatchNormalization(), layers.Activation('relu'),
        layers.MaxPooling2D(2,2), layers.Dropout(0.25),

        # Dense
        layers.Flatten(),
        layers.Dense(512, activation='relu'), layers.BatchNormalization(), layers.Dropout(0.5),
        layers.Dense(256, activation='relu'), layers.BatchNormalization(), layers.Dropout(0.5),
        layers.Dense(7,   activation='softmax')
    ])
    model.compile(
        optimizer=keras.optimizers.Adam(0.001),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )
    return model

def main():
    print("="*60)
    print("  FitPulse Pro — Emotion Model Training")
    print("="*60)

    if not os.path.isdir(TRAIN_DIR):
        print(f"❌ Training data not found at: {TRAIN_DIR}")
        print("   Place FER2013 dataset there and re-run.")
        return

    # Data generators
    train_gen = ImageDataGenerator(
        rescale=1./255, rotation_range=15,
        width_shift_range=0.1, height_shift_range=0.1,
        shear_range=0.1, zoom_range=0.1, horizontal_flip=True
    ).flow_from_directory(
        TRAIN_DIR, target_size=IMG_SIZE, color_mode='grayscale',
        batch_size=BATCH_SIZE, class_mode='categorical', shuffle=True
    )

    val_gen = ImageDataGenerator(rescale=1./255).flow_from_directory(
        VAL_DIR, target_size=IMG_SIZE, color_mode='grayscale',
        batch_size=BATCH_SIZE, class_mode='categorical', shuffle=False
    )

    print(f"\nTraining samples : {train_gen.samples}")
    print(f"Validation samples: {val_gen.samples}")
    print(f"Classes          : {train_gen.class_indices}\n")

    model = build_model()
    model.summary()

    callbacks = [
        keras.callbacks.ModelCheckpoint(MODEL_OUT, monitor='val_accuracy',
                                        save_best_only=True, verbose=1),
        keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5,
                                          patience=5, min_lr=1e-7, verbose=1),
        keras.callbacks.EarlyStopping(monitor='val_loss', patience=15,
                                      restore_best_weights=True, verbose=1)
    ]

    model.fit(train_gen, validation_data=val_gen,
              epochs=EPOCHS, callbacks=callbacks, verbose=1)

    print(f"\n✅ Training complete! Model saved: {MODEL_OUT}")


if __name__ == '__main__':
    main()
