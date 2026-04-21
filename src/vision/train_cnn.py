"""
Final CNN Training Script
Explainable AI for Drug Authenticity Verification (ExDAV)

Purpose:
- Train a lightweight CNN to classify drug packaging as
  'genuine' or 'counterfeit'
- Visual evidence will be used by the ontology reasoning layer

Author: MSc Research – Final Implementation
"""

import os
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam

# -------------------------------
# PATH SETUP
# -------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(BASE_DIR, "dataset", "images")
MODEL_PATH = os.path.join(BASE_DIR, "src", "vision", "cnn_visual_model.h5")

# -------------------------------
# TRAINING PARAMETERS
# -------------------------------
IMG_SIZE = 224
BATCH_SIZE = 16
EPOCHS = 10
LEARNING_RATE = 0.0001

# -------------------------------
# DATA GENERATORS
# -------------------------------
datagen = ImageDataGenerator(
    rescale=1.0 / 255,
    validation_split=0.2
)

train_generator = datagen.flow_from_directory(
    DATASET_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
    class_mode="categorical",
    subset="training"
)

validation_generator = datagen.flow_from_directory(
    DATASET_DIR,
    target_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
    class_mode="categorical",
    subset="validation"
)

print("Class labels:", train_generator.class_indices)

# -------------------------------
# MODEL: TRANSFER LEARNING
# -------------------------------
base_model = MobileNetV2(
    weights="imagenet",
    include_top=False,
    input_shape=(IMG_SIZE, IMG_SIZE, 3)
)

# Freeze base layers
base_model.trainable = False

x = base_model.output
x = GlobalAveragePooling2D()(x)
x = Dense(128, activation="relu")(x)
x = Dropout(0.3)(x)
output = Dense(train_generator.num_classes, activation="softmax")(x)

model = Model(inputs=base_model.input, outputs=output)

model.compile(
    optimizer=Adam(learning_rate=LEARNING_RATE),
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# -------------------------------
# TRAIN MODEL
# -------------------------------
print("\n🔹 Starting CNN training...\n")

history = model.fit(
    train_generator,
    validation_data=validation_generator,
    epochs=EPOCHS
)

# -------------------------------
# SAVE MODEL
# -------------------------------
model.save(MODEL_PATH)

print("\n✅ CNN training completed successfully")
print(f"Model saved at: {MODEL_PATH}")
