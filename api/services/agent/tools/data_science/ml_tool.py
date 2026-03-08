from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)

from .quality import _apply_cleaning_steps, _missing_dataset_result, _plan_dataset_cleaning_with_llm
from .shared import _as_float, _as_int, _import_pandas, _infer_problem_type, _limit_rows, _load_dataframe, _trace_event


class DataScienceModelTrainTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.ml.train",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Train and evaluate classical ML models for tabular data.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        del prompt
        events: list[ToolTraceEvent] = []
        df, source_label, warnings, source_ref = _load_dataframe(context=context, params=params)
        if df is None:
            return _missing_dataset_result(
                warnings,
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        target = str(params.get("target") or params.get("target_column") or "").strip()
        if not target:
            return _missing_dataset_result(
                warnings + ["ML training requires `target` or `target_column`."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )
        if target not in df.columns:
            return _missing_dataset_result(
                warnings + [f"Target column `{target}` was not found in dataset."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        max_rows = max(200, min(_as_int(params.get("max_rows"), 50000), 250000))
        df, truncated = _limit_rows(df, max_rows=max_rows)
        row_count_before_cleaning = int(len(df))
        col_count = int(len(df.columns))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="prepare_request",
                title="Prepare training dataset",
                detail=f"Loaded {row_count_before_cleaning} rows and {col_count} columns",
                data={
                    "row_count": row_count_before_cleaning,
                    "column_count": col_count,
                    "target": target,
                },
            )
        )

        features_raw = params.get("features")
        if isinstance(features_raw, list) and features_raw:
            feature_cols = [str(item).strip() for item in features_raw if str(item).strip() in df.columns]
        else:
            feature_cols = [column for column in df.columns if column != target]
        if not feature_cols:
            return _missing_dataset_result(
                warnings + ["No usable feature columns were found."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        requested_problem_type = str(params.get("problem_type") or "").strip().lower()
        required_numeric = [target] if requested_problem_type == "regression" else []
        required_columns = [target, *feature_cols]
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_started",
                title="Analyze dataset quality",
                detail="LLM planning cleanup steps for model training",
                data={"workflow": "ml_training", "target": target},
            )
        )
        quality_issues, cleaning_plan, llm_cleaning_used = _plan_dataset_cleaning_with_llm(
            df=df,
            workflow="ml_training",
            required_numeric=required_numeric,
            required_columns=required_columns,
            context_payload={
                "target": target,
                "features": feature_cols[:40],
                "problem_type_requested": requested_problem_type or "auto",
            },
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_completed",
                title="Dataset quality analysis complete",
                detail=f"Issues: {len(quality_issues)} | planned steps: {len(cleaning_plan)}",
                data={
                    "issues_count": len(quality_issues),
                    "planned_cleaning_steps": len(cleaning_plan),
                    "llm_used": llm_cleaning_used,
                },
            )
        )
        pd = _import_pandas()
        if pd is not None:
            df, cleaning_applied, cleaning_warnings = _apply_cleaning_steps(
                pd=pd,
                df=df,
                steps=cleaning_plan,
            )
            warnings.extend(cleaning_warnings)
        else:
            cleaning_applied = []
        for step in cleaning_applied:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title=f"Clean: {step.get('operation')}",
                    detail=f"Rows {step.get('rows_before')} -> {step.get('rows_after')}",
                    data={
                        "operation": step.get("operation"),
                        "rows_changed": step.get("rows_changed"),
                        "columns": step.get("columns"),
                    },
                )
            )

        row_count_after_cleaning = int(len(df))
        if target not in df.columns:
            return _missing_dataset_result(
                warnings + [f"Target column `{target}` is unavailable after cleaning."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )
        df = df.dropna(subset=[target]).copy()
        feature_cols = [column for column in feature_cols if column in df.columns]
        if not feature_cols:
            return _missing_dataset_result(
                warnings + ["No usable feature columns were found after cleaning."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        X = df[feature_cols]
        y = df[target]
        if len(X) < 20:
            return _missing_dataset_result(
                warnings + ["At least 20 non-empty rows are recommended for model training."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        problem_type = _infer_problem_type(y, requested_problem_type)
        model_name = str(params.get("model") or "").strip().lower()
        test_size = min(0.45, max(0.1, _as_float(params.get("test_size"), 0.2)))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="normalize_response",
                title="Validate training request",
                detail=f"problem={problem_type}, features={len(feature_cols)}",
                data={
                    "problem_type": problem_type,
                    "feature_count": len(feature_cols),
                    "rows_before_cleaning": row_count_before_cleaning,
                    "rows_after_cleaning": row_count_after_cleaning,
                },
            )
        )

        try:
            from sklearn.compose import ColumnTransformer
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LinearRegression, LogisticRegression
            from sklearn.metrics import (
                accuracy_score,
                f1_score,
                mean_absolute_error,
                mean_squared_error,
                r2_score,
            )
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
        except Exception:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_failed",
                    title="Dependency missing",
                    detail="scikit-learn is not installed",
                    data={"remediation": "Install scikit-learn and retry."},
                )
            )
            return ToolExecutionResult(
                summary="ML training unavailable in current environment.",
                content=(
                    "Missing dependency: `scikit-learn`.\n"
                    "Install with `pip install scikit-learn` and rerun."
                ),
                data={
                    "available": False,
                    "target": target,
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                },
                sources=[source_ref] if source_ref else [],
                next_steps=["Install scikit-learn and retry `data.science.ml.train`."],
                events=events,
            )

        numeric_cols = list(X.select_dtypes(include="number").columns)
        categorical_cols = [column for column in feature_cols if column not in numeric_cols]
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "num",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    numeric_cols,
                ),
                (
                    "cat",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    categorical_cols,
                ),
            ]
        )

        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_started",
                title="Train ML model",
                detail="Fitting sklearn pipeline",
                data={"problem_type": problem_type, "model_request": model_name or "default"},
            )
        )
        if problem_type == "classification":
            if model_name in {"random_forest", "rf", "forest"}:
                estimator = RandomForestClassifier(n_estimators=250, random_state=42)
                model_label = "random_forest_classifier"
            else:
                estimator = LogisticRegression(max_iter=2000)
                model_label = "logistic_regression"
        else:
            if model_name in {"random_forest", "rf", "forest"}:
                estimator = RandomForestRegressor(n_estimators=250, random_state=42)
                model_label = "random_forest_regressor"
            else:
                estimator = LinearRegression()
                model_label = "linear_regression"

        pipeline = Pipeline(steps=[("preprocess", preprocessor), ("model", estimator)])
        stratify = y if problem_type == "classification" and int(y.nunique(dropna=True)) >= 2 else None
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=test_size,
                random_state=42,
                stratify=stratify,
            )
            pipeline.fit(X_train, y_train)
            predictions = pipeline.predict(X_test)
        except Exception as exc:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="api_call_failed",
                    title="Train ML model failed",
                    detail=str(exc),
                    data={
                        "remediation": "Check target/feature types and missing values, then retry.",
                    },
                )
            )
            return ToolExecutionResult(
                summary="ML training failed.",
                content=(
                    "Model training could not complete with the provided dataset/params.\n"
                    f"- Error: {str(exc)}"
                ),
                data={
                    "target": target,
                    "problem_type": problem_type,
                    "model": model_label,
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                    "error_type": "training_failed",
                },
                sources=[source_ref] if source_ref else [],
                next_steps=[
                    "Check target/feature types and missing values.",
                    "Try setting `problem_type` explicitly.",
                ],
                events=events,
            )

        metrics: dict[str, float] = {}
        if problem_type == "classification":
            metrics["accuracy"] = float(accuracy_score(y_test, predictions))
            try:
                metrics["f1_macro"] = float(f1_score(y_test, predictions, average="macro"))
            except Exception:
                pass
        else:
            mse = float(mean_squared_error(y_test, predictions))
            metrics["rmse"] = float(mse**0.5)
            metrics["mae"] = float(mean_absolute_error(y_test, predictions))
            metrics["r2"] = float(r2_score(y_test, predictions))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_completed",
                title="Train ML model completed",
                detail=f"{problem_type} metrics ready",
                data={"model": model_label, "metrics": metrics},
            )
        )

        cross_val_results: dict[str, Any] = {}
        tune_results: dict[str, Any] = {}
        cross_val_param = str(params.get("cross_val") or "").lower() in {"true", "1", "yes"}
        tune_param = str(params.get("tune") or "").lower() in {"true", "1", "yes"}

        if cross_val_param:
            try:
                from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score
                n_splits = 5
                cv_scoring = "accuracy" if problem_type == "classification" else "r2"
                cv = (
                    StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                    if problem_type == "classification"
                    else KFold(n_splits=n_splits, shuffle=True, random_state=42)
                )
                cv_scores = cross_val_score(pipeline, X, y, cv=cv, scoring=cv_scoring)
                cross_val_results = {
                    "cv_mean": round(float(cv_scores.mean()), 5),
                    "cv_std": round(float(cv_scores.std()), 5),
                    "cv_scores": [round(float(s), 5) for s in cv_scores.tolist()],
                    "scoring": cv_scoring,
                    "n_splits": n_splits,
                }
                events.append(
                    _trace_event(
                        tool_id=self.metadata.tool_id,
                        event_type="tool_progress",
                        title="Cross-validation complete",
                        detail=f"{cv_scoring} mean={cross_val_results['cv_mean']:.5f} ±{cross_val_results['cv_std']:.5f}",
                        data=cross_val_results,
                    )
                )
            except Exception as exc:
                warnings.append(f"Cross-validation failed: {str(exc)}")

        if tune_param:
            try:
                from sklearn.model_selection import GridSearchCV
                if model_label == "logistic_regression":
                    param_grid: dict[str, Any] = {"model__C": [0.01, 0.1, 1, 10]}
                elif model_label in {"random_forest_classifier", "random_forest_regressor"}:
                    param_grid = {
                        "model__n_estimators": [50, 100, 200],
                        "model__max_depth": [None, 5, 10],
                    }
                else:
                    param_grid = {}
                if param_grid:
                    tune_scoring = "accuracy" if problem_type == "classification" else "r2"
                    gs = GridSearchCV(pipeline, param_grid, cv=3, scoring=tune_scoring, n_jobs=-1)
                    gs.fit(X_train, y_train)
                    tune_results = {
                        "best_params": gs.best_params_,
                        "best_cv_score": round(float(gs.best_score_), 5),
                        "scoring": tune_scoring,
                    }
                    events.append(
                        _trace_event(
                            tool_id=self.metadata.tool_id,
                            event_type="tool_progress",
                            title="Hyperparameter tuning complete",
                            detail=f"best_cv_score={tune_results['best_cv_score']:.5f}",
                            data=tune_results,
                        )
                    )
            except Exception as exc:
                warnings.append(f"Hyperparameter tuning failed: {str(exc)}")

        context.settings["__latest_ml_training"] = {
            "target": target,
            "problem_type": problem_type,
            "model": model_label,
            "metrics": metrics,
            "rows": int(len(df)),
            "features": len(feature_cols),
        }

        notes = [f"- {item}" for item in warnings[:6]]
        if truncated:
            notes.append(f"- Dataset was truncated to first {len(df)} row(s).")
        if cleaning_applied:
            notes.append(
                f"- Cleaning changed rows from {row_count_before_cleaning} to {int(len(df))}."
            )
        metric_lines = [f"- {name}: {value:.5f}" for name, value in metrics.items()]

        content_lines = [
            "### Classical ML Training",
            f"- Source: {source_label or 'payload'}",
            f"- Target: {target}",
            f"- Problem type: {problem_type}",
            f"- Model: {model_label}",
            f"- Features: {len(feature_cols)}",
            f"- Train rows: {len(X_train)}",
            f"- Test rows: {len(X_test)}",
            f"- LLM cleaning planner used: {'yes' if llm_cleaning_used else 'fallback'}",
            "",
            "### Metrics",
            *(metric_lines or ["- No metrics were produced."]),
        ]
        if cross_val_results:
            content_lines.extend([
                "", "### Cross-Validation (5-fold)",
                f"- Scoring: {cross_val_results['scoring']}",
                f"- Mean: {cross_val_results['cv_mean']:.5f} ± {cross_val_results['cv_std']:.5f}",
                f"- Fold scores: {', '.join(str(s) for s in cross_val_results['cv_scores'])}",
            ])
        if tune_results:
            content_lines.extend([
                "", "### Hyperparameter Tuning",
                f"- Best CV score: {tune_results['best_cv_score']:.5f}",
                *[f"- {k}: {v}" for k, v in tune_results.get("best_params", {}).items()],
            ])
        if quality_issues:
            content_lines.extend(["", "### Data Quality Issues", *[f"- {item}" for item in quality_issues[:8]]])
        if notes:
            content_lines.extend(["", "### Notes", *notes])

        return ToolExecutionResult(
            summary=f"Trained {model_label} on {len(df)} row(s).",
            content="\n".join(content_lines),
            data={
                "target": target,
                "problem_type": problem_type,
                "model": model_label,
                "feature_columns": feature_cols,
                "feature_count": len(feature_cols),
                "train_rows": len(X_train),
                "test_rows": len(X_test),
                "metrics": metrics,
                "cross_val": cross_val_results,
                "best_params": tune_results.get("best_params", {}),
                "tune": tune_results,
                "warnings": warnings,
                "truncated": truncated,
                "quality_issues": quality_issues,
                "cleaning_plan": cleaning_plan,
                "cleaning_applied": cleaning_applied,
                "llm_cleaning_used": llm_cleaning_used,
                "rows_before_cleaning": row_count_before_cleaning,
                "rows_after_cleaning": int(len(df)),
                "rows_removed_by_cleaning": max(0, row_count_before_cleaning - int(len(df))),
            },
            sources=[source_ref] if source_ref else [],
            next_steps=[
                "Tune hyperparameters and compare metrics.",
                "Run `data.science.deep_learning.train` as a neural baseline.",
            ],
            events=events
            + [
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title="Train classical ML model",
                    detail=f"{model_label} ({problem_type})",
                    data={"target": target, "metrics": metrics},
                )
            ],
        )
