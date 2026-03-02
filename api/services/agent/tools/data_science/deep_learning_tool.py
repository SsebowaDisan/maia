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


class DataScienceDeepLearningTrainTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.deep_learning.train",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Train a compact neural baseline on numeric tabular features.",
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
                warnings + ["Deep-learning training requires `target` or `target_column`."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )
        if target not in df.columns:
            return _missing_dataset_result(
                warnings + [f"Target column `{target}` was not found in dataset."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        max_rows = max(300, min(_as_int(params.get("max_rows"), 25000), 150000))
        df, truncated = _limit_rows(df, max_rows=max_rows)
        row_count_before_cleaning = int(len(df))
        col_count = int(len(df.columns))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="prepare_request",
                title="Prepare deep-learning dataset",
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
        required_numeric = list(feature_cols)
        if requested_problem_type == "regression":
            required_numeric.append(target)
        required_columns = [target, *feature_cols]
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="llm.dataset_cleaning_started",
                title="Analyze dataset quality",
                detail="LLM planning cleanup steps for deep-learning workflow",
                data={"workflow": "deep_learning_training", "target": target},
            )
        )
        quality_issues, cleaning_plan, llm_cleaning_used = _plan_dataset_cleaning_with_llm(
            df=df,
            workflow="deep_learning_training",
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
                warnings + ["No feature columns remained after cleaning."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        numeric_frame = df[feature_cols].select_dtypes(include="number").copy()
        numeric_frame = numeric_frame.fillna(numeric_frame.median(numeric_only=True))
        if numeric_frame.empty:
            return _missing_dataset_result(
                warnings + ["Deep-learning baseline requires at least one numeric feature column."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )
        if len(numeric_frame) < 40:
            return _missing_dataset_result(
                warnings + ["At least 40 rows are recommended for deep-learning training."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        y_series = df[target]
        problem_type = _infer_problem_type(y_series, requested_problem_type)
        row_count_after_cleaning = int(len(df))
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="normalize_response",
                title="Validate training request",
                detail=f"problem={problem_type}, numeric_features={numeric_frame.shape[1]}",
                data={
                    "problem_type": problem_type,
                    "feature_count": int(numeric_frame.shape[1]),
                    "rows_before_cleaning": row_count_before_cleaning,
                    "rows_after_cleaning": row_count_after_cleaning,
                },
            )
        )

        try:
            import numpy as np
            import torch
            import torch.nn as nn
            from torch.utils.data import DataLoader, TensorDataset
        except Exception:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_failed",
                    title="Dependency missing",
                    detail="torch is not installed",
                    data={"remediation": "Install torch and retry."},
                )
            )
            return ToolExecutionResult(
                summary="Deep-learning training unavailable in current environment.",
                content=(
                    "Missing dependency: `torch`.\n"
                    "Install with `pip install torch` and rerun."
                ),
                data={
                    "available": False,
                    "target": target,
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                },
                sources=[source_ref] if source_ref else [],
                next_steps=["Install torch and retry `data.science.deep_learning.train`."],
                events=events,
            )

        x_np = numeric_frame.to_numpy(dtype="float32")

        if problem_type == "classification":
            y_codes, classes = y_series.astype(str).factorize()
            if len(classes) < 2:
                return _missing_dataset_result(
                    warnings + ["Classification needs at least two target classes."],
                    tool_id=self.metadata.tool_id,
                    events_prefix=events,
                )
            y_np = y_codes.astype("int64")
            output_dim = int(len(classes))
        else:
            try:
                y_np = y_series.astype(float).to_numpy(dtype="float32")
            except Exception:
                return _missing_dataset_result(
                    warnings + ["Regression target must be numeric for deep-learning training."],
                    tool_id=self.metadata.tool_id,
                    events_prefix=events,
                )
            output_dim = 1

        test_size = min(0.45, max(0.1, _as_float(params.get("test_size"), 0.2)))
        test_count = max(1, int(len(x_np) * test_size))
        permutation = np.random.default_rng(seed=42).permutation(len(x_np))
        test_idx = permutation[:test_count]
        train_idx = permutation[test_count:]
        if len(train_idx) < 1:
            return _missing_dataset_result(
                warnings + ["Not enough rows left for training split."],
                tool_id=self.metadata.tool_id,
                events_prefix=events,
            )

        x_train = torch.tensor(x_np[train_idx], dtype=torch.float32)
        x_test = torch.tensor(x_np[test_idx], dtype=torch.float32)
        if problem_type == "classification":
            y_train = torch.tensor(y_np[train_idx], dtype=torch.long)
            y_test = torch.tensor(y_np[test_idx], dtype=torch.long)
        else:
            y_train = torch.tensor(y_np[train_idx], dtype=torch.float32).view(-1, 1)
            y_test = torch.tensor(y_np[test_idx], dtype=torch.float32).view(-1, 1)

        hidden_dim = max(8, min(_as_int(params.get("hidden_dim"), 48), 512))
        model = nn.Sequential(
            nn.Linear(int(x_train.shape[1]), hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, max(4, hidden_dim // 2)),
            nn.ReLU(),
            nn.Linear(max(4, hidden_dim // 2), output_dim),
        )
        criterion = nn.CrossEntropyLoss() if problem_type == "classification" else nn.MSELoss()
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=max(1e-5, min(_as_float(params.get("lr"), 1e-3), 0.1)),
        )
        epochs = max(3, min(_as_int(params.get("epochs"), 25), 300))
        batch_size = max(8, min(_as_int(params.get("batch_size"), 32), 512))

        train_loader = DataLoader(
            TensorDataset(x_train, y_train),
            batch_size=batch_size,
            shuffle=True,
        )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_started",
                title="Train deep-learning model",
                detail="Fitting neural baseline",
                data={"problem_type": problem_type, "epochs": epochs},
            )
        )
        try:
            model.train()
            last_loss = 0.0
            for _ in range(epochs):
                for batch_x, batch_y in train_loader:
                    optimizer.zero_grad()
                    output = model(batch_x)
                    loss = criterion(output, batch_y)
                    loss.backward()
                    optimizer.step()
                    last_loss = float(loss.item())

            model.eval()
            with torch.no_grad():
                test_output = model(x_test)
                if problem_type == "classification":
                    predicted = torch.argmax(test_output, dim=1)
                    accuracy = float((predicted == y_test).float().mean().item())
                    metrics = {"accuracy": accuracy, "final_train_loss": last_loss}
                else:
                    mse = float(torch.mean((test_output - y_test) ** 2).item())
                    metrics = {
                        "rmse": float(mse**0.5),
                        "mae": float(torch.mean(torch.abs(test_output - y_test)).item()),
                        "final_train_loss": last_loss,
                    }
        except Exception as exc:
            events.append(
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="api_call_failed",
                    title="Train deep-learning model failed",
                    detail=str(exc),
                    data={
                        "remediation": "Check numeric features/target values and retry with fewer epochs.",
                    },
                )
            )
            return ToolExecutionResult(
                summary="Deep-learning training failed.",
                content=(
                    "Neural training could not complete with the provided dataset/params.\n"
                    f"- Error: {str(exc)}"
                ),
                data={
                    "target": target,
                    "problem_type": problem_type,
                    "quality_issues": quality_issues,
                    "cleaning_plan": cleaning_plan,
                    "cleaning_applied": cleaning_applied,
                    "error_type": "training_failed",
                },
                sources=[source_ref] if source_ref else [],
                next_steps=[
                    "Check numeric features and target quality.",
                    "Reduce epochs or simplify dataset.",
                ],
                events=events,
            )
        events.append(
            _trace_event(
                tool_id=self.metadata.tool_id,
                event_type="api_call_completed",
                title="Train deep-learning model completed",
                detail=f"{problem_type} metrics ready",
                data={"metrics": metrics, "epochs": epochs},
            )
        )

        context.settings["__latest_deep_learning_training"] = {
            "target": target,
            "problem_type": problem_type,
            "metrics": metrics,
            "epochs": epochs,
            "feature_count": int(numeric_frame.shape[1]),
            "rows": int(len(df)),
        }

        notes = [f"- {item}" for item in warnings[:6]]
        if truncated:
            notes.append(f"- Dataset was truncated to first {len(df)} row(s).")
        if cleaning_applied:
            notes.append(
                f"- Cleaning changed rows from {row_count_before_cleaning} to {int(len(df))}."
            )
        metric_lines = [f"- {name}: {value:.6f}" for name, value in metrics.items()]

        content_lines = [
            "### Deep Learning Training",
            f"- Source: {source_label or 'payload'}",
            f"- Target: {target}",
            f"- Problem type: {problem_type}",
            f"- Epochs: {epochs}",
            f"- Numeric features used: {numeric_frame.shape[1]}",
            f"- Train rows: {len(train_idx)}",
            f"- Test rows: {len(test_idx)}",
            f"- LLM cleaning planner used: {'yes' if llm_cleaning_used else 'fallback'}",
            "",
            "### Metrics",
            *metric_lines,
        ]
        if quality_issues:
            content_lines.extend(["", "### Data Quality Issues", *[f"- {item}" for item in quality_issues[:8]]])
        if notes:
            content_lines.extend(["", "### Notes", *notes])

        return ToolExecutionResult(
            summary=f"Trained neural baseline on {len(df)} row(s).",
            content="\n".join(content_lines),
            data={
                "target": target,
                "problem_type": problem_type,
                "metrics": metrics,
                "epochs": epochs,
                "feature_count": int(numeric_frame.shape[1]),
                "feature_columns": list(numeric_frame.columns),
                "train_rows": len(train_idx),
                "test_rows": len(test_idx),
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
                "Compare with `data.science.ml.train` metrics.",
                "Tune epochs/lr/hidden_dim and feature engineering.",
            ],
            events=events
            + [
                _trace_event(
                    tool_id=self.metadata.tool_id,
                    event_type="tool_progress",
                    title="Train deep-learning baseline",
                    detail=f"{problem_type} model for {epochs} epoch(s)",
                    data={"target": target, "metrics": metrics},
                )
            ],
        )
