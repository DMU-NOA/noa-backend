import os
import joblib
import pandas as pd

from pathlib import Path

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


BASE_DIR = Path(__file__).resolve().parent

DATA_PATH = (
    BASE_DIR
    / "congestion_training_dataset.csv"
)

MODEL_PATH = (
    BASE_DIR
    / "congestion_model.pkl"
)


def train_model():

    print()
    print("================================")
    print("혼잡도 Random Forest 학습 시작")
    print("================================")

    df = pd.read_csv(DATA_PATH)

    print(f"전체 데이터: {len(df)}건")

    # -----------------------------------
    # 사용할 feature
    # -----------------------------------

    feature_columns = [
        "category",
        "mapx",
        "mapy",
        "hour",
        "day_of_week"
    ]

    target_column = "congestion_label"

    X = df[feature_columns]
    y = df[target_column]

    print()
    print("혼잡도 클래스 분포")
    print(y.value_counts().sort_index())

    # -----------------------------------
    # Train / Test 분리
    # -----------------------------------

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.25,
            random_state=42,
            stratify=y
        )
    )

    categorical_features = [
        "category"
    ]

    numeric_features = [
        "mapx",
        "mapy",
        "hour",
        "day_of_week"
    ]

    # -----------------------------------
    # 전처리
    # -----------------------------------

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "category",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
                categorical_features
            ),
            (
                "numeric",
                "passthrough",
                numeric_features
            )
        ]
    )

    # -----------------------------------
    # Random Forest
    # -----------------------------------

    model = RandomForestClassifier(
        n_estimators=300,

        # 현재 데이터 불균형 대응
        class_weight="balanced",

        random_state=42,

        n_jobs=-1
    )

    pipeline = Pipeline(
        steps=[
            (
                "preprocessor",
                preprocessor
            ),
            (
                "model",
                model
            )
        ]
    )

    # -----------------------------------
    # 학습
    # -----------------------------------

    pipeline.fit(
        X_train,
        y_train
    )

    # -----------------------------------
    # 테스트
    # -----------------------------------

    y_pred = pipeline.predict(
        X_test
    )

    accuracy = accuracy_score(
        y_test,
        y_pred
    )

    print()
    print("================================")
    print("1차 테스트 결과")
    print("================================")

    print(
        f"Accuracy: "
        f"{accuracy:.4f}"
    )

    print()
    print("Classification Report")

    print(
        classification_report(
            y_test,
            y_pred,
            labels=[0, 1, 2, 3],
            target_names=[
                "여유",
                "보통",
                "약간 붐빔",
                "붐빔"
            ],
            zero_division=0
        )
    )

    print()
    print("Confusion Matrix")

    print(
        confusion_matrix(
            y_test,
            y_pred,
            labels=[0, 1, 2, 3]
        )
    )

    # -----------------------------------
    # 모델 저장
    # -----------------------------------

    joblib.dump(
        pipeline,
        MODEL_PATH
    )

    print()
    print("================================")
    print("모델 저장 완료")
    print(MODEL_PATH)
    print("================================")


if __name__ == "__main__":
    train_model()