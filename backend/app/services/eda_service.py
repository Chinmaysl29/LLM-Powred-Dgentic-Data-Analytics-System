"""Service for Exploratory Data Analysis (EDA) Agent.

Provides deep, automated exploratory analysis answering:
- What does this dataset contain? (Understanding, domain, data types)
- What statistical characteristics exist? (Summaries, distributions, missingness)
- What anomalies, outliers, and correlations exist?
- What time-based trends and seasonality exist?
- What actionable business insights emerge from the data?
"""

import hashlib
import logging
import time
from typing import Any
import numpy as np
import pandas as pd
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.exceptions import DataRetrievalError, ValidationException
from backend.app.database.postgres import get_db_session
from backend.app.schemas.eda import (
    BusinessInsight,
    CardinalityLevel,
    CategoryDetail,
    ColumnDistribution,
    ColumnMissingDetail,
    ColumnOutliers,
    CorrelationAnalysis,
    CorrelationPair,
    DatasetSummary,
    DistributionType,
    EDAResults,
    MissingValuesAnalysis,
    NumericColumnStatistics,
    OutlierDetectionDetail,
    TrendAnalysis,
    TrendDirection,
    TrendPattern,
)
from backend.app.services.data_retrieval_service import (
    DataRetrievalService,
    get_data_retrieval_service,
)

logger = logging.getLogger(__name__)


# Keywords for heuristic domain and dataset type classification
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "sales": [
        "sale", "sales", "order", "revenue", "price", "discount", "deal",
        "product", "invoice", "subtotal", "gross", "quantity_sold"
    ],
    "marketing": [
        "campaign", "ad", "click", "ctr", "cpc", "lead", "channel",
        "impression", "conversion", "spend", "cost_per", "utm"
    ],
    "finance": [
        "account", "balance", "asset", "liability", "expense", "profit",
        "margin", "cash", "credit", "debit", "equity", "tax", "ebitda"
    ],
    "inventory": [
        "stock", "sku", "warehouse", "inventory", "reorder", "supplier",
        "unit_cost", "safety_stock", "shelf", "replenishment"
    ],
    "customer": [
        "churn", "subscriber", "user_id", "customer_id", "email", "age",
        "gender", "tenure", "segment", "loyalty", "lifetime_value", "clv"
    ],
    "operations": [
        "shipment", "delivery", "logistics", "latency", "failure", "uptime",
        "maintenance", "ticket", "sla", "transit", "incident"
    ],
}


class EDAService:
    """Core analytical service for automated Exploratory Data Analysis."""

    def __init__(self, retrieval_service: DataRetrievalService | None = None) -> None:
        self._retrieval_service = retrieval_service

    def analyze_dataframe(
        self,
        df: pd.DataFrame,
        dataset_id: str | None = None,
        max_rows_for_full: int = 1_000_000,
        sample_size_for_large: int = 50_000,
    ) -> EDAResults:
        """Run comprehensive automated EDA on a pandas DataFrame.
        
        Applies performance tiering based on dataset size:
        - Small (<100k rows): Full EDA.
        - Medium (100k - 1M rows): Optimized vectorized EDA.
        - Large (>1M rows): Auto-sampling with is_sampled indicator.
        """
        start_time = time.perf_counter()
        logger.info("Starting EDA analysis for dataset_id=%s, initial shape=%s", dataset_id, df.shape)

        if df.empty:
            logger.warning("Empty dataframe provided to EDA service for dataset_id=%s", dataset_id)
            return self._build_empty_eda_results(dataset_id)

        # Performance Tiering: Auto-sample if over 1M rows
        is_sampled = False
        original_row_count = len(df)
        if original_row_count > max_rows_for_full:
            logger.info(
                "Dataset exceeds %d rows (%d rows). Applying sampling to %d rows for EDA.",
                max_rows_for_full, original_row_count, sample_size_for_large
            )
            df = df.sample(n=sample_size_for_large, random_state=42)
            is_sampled = True

        # 1. Dataset Understanding
        summary = self._detect_dataset_understanding(df, dataset_id, is_sampled, original_row_count)

        # 2. Statistical Summary
        statistics = self._calculate_statistical_summary(df, summary.numeric_columns)

        # 3. Missing Value Analysis
        missing_values = self._analyze_missing_values(df)

        # 4. Distribution Analysis
        distributions = self._analyze_distributions(df, summary.numeric_columns)

        # 5. Outlier Detection
        outliers = self._detect_outliers(df, summary.numeric_columns)

        # 6. Correlation Analysis
        correlations = self._analyze_correlations(df, summary.numeric_columns)

        # 7. Trend Detection
        trends = self._detect_trends(df, summary.datetime_columns, summary.numeric_columns)

        # 8. Categorical Analysis
        categorical_analysis = self._analyze_categoricals(df, summary.categorical_columns)

        # 9. Business Insight Generation
        business_insights = self._generate_business_insights(
            df=df,
            summary=summary,
            statistics=statistics,
            missing_values=missing_values,
            distributions=distributions,
            outliers=outliers,
            correlations=correlations,
            trends=trends,
            categorical_analysis=categorical_analysis,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Completed EDA analysis for dataset_id=%s in %.2fms (numeric_cols=%d, insights=%d)",
            dataset_id, duration_ms, len(statistics), len(business_insights)
        )

        return EDAResults(
            chart_manifest=__import__("backend.app.services.eda_charts", fromlist=["build_charts"]).build_charts(df, dataset_id),
            dataset_summary=summary,
            statistics=statistics,
            missing_values=missing_values,
            distributions=distributions,
            outliers=outliers,
            correlations=correlations,
            trends=trends,
            categorical_analysis=categorical_analysis,
            business_insights=business_insights,
        )

    async def analyze_dataset(
        self,
        dataset_id: str,
        version_number: int | None = None,
        sample_size: int | None = None,
        filters=None,
    ) -> EDAResults:
        """Load dataset from retrieval service and execute full EDA."""
        if not self._retrieval_service:
            raise DataRetrievalError("DataRetrievalService not injected into EDAService")

        logger.info("Retrieving dataset %s (version=%s) for EDA", dataset_id, version_number)
        from backend.app.services.eda_charts import build_charts
        _, version, _, _, _ = self._retrieval_service.discover(dataset_id, version_number)
        pinned_version = version.version_number
        df, _ = self._retrieval_service.load_dataframe(
            dataset_id=dataset_id, version_number=pinned_version, filters=filters, sample_size=0,
        )
        source_path = self._retrieval_service.storage_service.retrieve_file(version.storage_path)
        with source_path.open('rb') as source:
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
        results = self.analyze_dataframe(df, dataset_id=dataset_id)
        results.chart_manifest = build_charts(df, dataset_id,
            version=pinned_version, source_data_reference=f"dataset:{dataset_id}:version:{pinned_version}",
            source_checksum=checksum, applied_filters=filters.model_dump(exclude_none=True) if filters else {})
        return results

    # -------------------------------------------------------------------------
    # Internal Engine Implementations
    # -------------------------------------------------------------------------

    def _detect_dataset_understanding(
        self,
        df: pd.DataFrame,
        dataset_id: str | None,
        is_sampled: bool,
        total_rows: int,
    ) -> DatasetSummary:
        """Analyze column names and data types to infer business domain and dataset type."""
        cols_lower = [str(col).lower() for col in df.columns]
        
        # Classify columns by type
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Check datetime columns
        datetime_cols: list[str] = []
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                datetime_cols.append(col)
            elif "date" in str(col).lower() or "time" in str(col).lower() or "timestamp" in str(col).lower():
                # Attempt conversion on sample
                sample = df[col].dropna().head(10)
                if not sample.empty:
                    try:
                        pd.to_datetime(sample)
                        datetime_cols.append(col)
                    except Exception:
                        pass

        categorical_cols = [
            col for col in df.columns
            if col not in numeric_cols and col not in datetime_cols
        ]

        # Score domains based on column keyword matches
        domain_scores: dict[str, int] = {domain: 0 for domain in DOMAIN_KEYWORDS}
        for col in cols_lower:
            for domain, keywords in DOMAIN_KEYWORDS.items():
                for kw in keywords:
                    if kw in col:
                        domain_scores[domain] += 1

        best_domain = max(domain_scores, key=domain_scores.get)
        best_score = domain_scores[best_domain]

        if best_score > 0:
            dataset_type = best_domain
            business_domain = f"{best_domain.capitalize()} Management"
        else:
            dataset_type = "general"
            business_domain = "General Tabular Data"

        data_categories = []
        if numeric_cols:
            data_categories.append("Quantitative Metrics")
        if categorical_cols:
            data_categories.append("Categorical Attributes")
        if datetime_cols:
            data_categories.append("Temporal Sequences")

        memory_usage_mb = round(float(df.memory_usage(deep=True).sum()) / (1024 * 1024), 2)

        return DatasetSummary(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            business_domain=business_domain,
            row_count=total_rows,
            column_count=len(df.columns),
            column_names=df.columns.tolist(),
            numeric_columns=numeric_cols,
            categorical_columns=categorical_cols,
            datetime_columns=datetime_cols,
            data_categories=data_categories,
            memory_usage_mb=memory_usage_mb,
            is_sampled=is_sampled,
        )

    def _calculate_statistical_summary(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> dict[str, NumericColumnStatistics]:
        """Compute count, mean, median, mode, std, variance, min, max, and quantiles."""
        summary: dict[str, NumericColumnStatistics] = {}

        for col in numeric_cols:
            series = df[col].dropna()
            if series.empty:
                continue

            modes = series.mode()
            mode_val = float(modes.iloc[0]) if not modes.empty else None

            count = int(series.count())
            mean = float(series.mean())
            median = float(series.median())
            std = float(series.std(ddof=1)) if count > 1 else 0.0
            variance = float(series.var(ddof=1)) if count > 1 else 0.0
            min_val = float(series.min())
            max_val = float(series.max())
            q25 = float(series.quantile(0.25))
            q75 = float(series.quantile(0.75))

            summary[col] = NumericColumnStatistics(
                count=count,
                mean=round(mean, 4),
                median=round(median, 4),
                mode=round(mode_val, 4) if mode_val is not None else None,
                std=round(std, 4),
                variance=round(variance, 4),
                min=round(min_val, 4),
                max=round(max_val, 4),
                q25=round(q25, 4),
                q75=round(q75, 4),
            )

        return summary

    def _analyze_missing_values(self, df: pd.DataFrame) -> MissingValuesAnalysis:
        """Calculate missing cell counts and percentages per column and overall."""
        total_cells = df.shape[0] * df.shape[1]
        total_missing = int(df.isna().sum().sum())
        missing_pct = round(float(total_missing / total_cells * 100), 2) if total_cells > 0 else 0.0

        affected_columns: list[str] = []
        column_details: dict[str, ColumnMissingDetail] = {}

        for col in df.columns:
            null_count = int(df[col].isna().sum())
            if null_count > 0:
                affected_columns.append(col)
                col_pct = round(float(null_count / len(df) * 100), 2)
                column_details[col] = ColumnMissingDetail(
                    missing_count=null_count,
                    missing_percentage=col_pct,
                )

        return MissingValuesAnalysis(
            total_missing_cells=total_missing,
            missing_percentage=missing_pct,
            affected_columns_count=len(affected_columns),
            affected_columns=affected_columns,
            column_details=column_details,
        )

    def _analyze_distributions(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> dict[str, ColumnDistribution]:
        """Classify distribution as normal, skewed, or uniform."""
        distributions: dict[str, ColumnDistribution] = {}

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 3:
                continue

            skew = float(series.skew())
            kurt = float(series.kurt())
            val_range = float(series.max() - series.min())

            # Check uniform distribution characteristics:
            # 1. Negative kurtosis (platykurtic, flatter than normal ~ -1.2 for continuous uniform)
            # 2. Standard deviation close to range / sqrt(12)
            is_uniform = False
            if val_range > 0 and kurt < -0.8 and abs(skew) < 0.35:
                theoretical_uniform_std = val_range / np.sqrt(12)
                actual_std = float(series.std())
                if abs(actual_std - theoretical_uniform_std) / theoretical_uniform_std < 0.25:
                    is_uniform = True

            if is_uniform:
                dist_type: DistributionType = "uniform"
                desc = f"Uniform distribution across range [{series.min():.2f}, {series.max():.2f}]"
                is_symmetric = True
            elif abs(skew) > 1.0:
                dist_type = "skewed"
                direction = "right (positive)" if skew > 0 else "left (negative)"
                desc = f"Skewed {direction} distribution (skewness: {skew:.2f})"
                is_symmetric = False
            elif abs(skew) <= 0.5 and abs(kurt) < 2.0:
                dist_type = "normal"
                desc = f"Approximately normal bell-curve distribution (skewness: {skew:.2f}, kurtosis: {kurt:.2f})"
                is_symmetric = True
            else:
                dist_type = "skewed"
                desc = f"Moderately skewed distribution (skewness: {skew:.2f})"
                is_symmetric = False

            distributions[col] = ColumnDistribution(
                distribution_type=dist_type,
                skewness=round(skew, 4),
                kurtosis=round(kurt, 4),
                is_symmetric=is_symmetric,
                description=desc,
            )

        return distributions

    def _detect_outliers(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> dict[str, ColumnOutliers]:
        """Perform outlier detection via both IQR and Z-score methods."""
        outliers_dict: dict[str, ColumnOutliers] = {}

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue

            # --- 1. IQR Method ---
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            iqr_lower = q1 - 1.5 * iqr
            iqr_upper = q3 + 1.5 * iqr

            iqr_mask = (series < iqr_lower) | (series > iqr_upper)
            iqr_outliers = series[iqr_mask]
            iqr_count = int(iqr_outliers.count())
            iqr_pct = round(float(iqr_count / len(series) * 100), 2)
            iqr_sample = [round(float(v), 4) for v in iqr_outliers.head(5).tolist()]

            iqr_detail = OutlierDetectionDetail(
                method="IQR (1.5x)",
                outlier_count=iqr_count,
                outlier_percentage=iqr_pct,
                lower_bound=round(iqr_lower, 4),
                upper_bound=round(iqr_upper, 4),
                sample_outliers=iqr_sample,
            )

            # --- 2. Z-Score Method ---
            mean = float(series.mean())
            std = float(series.std(ddof=1))
            if std > 0:
                z_scores = (series - mean) / std
                z_mask = z_scores.abs() > 3.0
                z_outliers = series[z_mask]
                z_count = int(z_outliers.count())
                z_pct = round(float(z_count / len(series) * 100), 2)
                z_lower = mean - 3.0 * std
                z_upper = mean + 3.0 * std
                z_sample = [round(float(v), 4) for v in z_outliers.head(5).tolist()]
            else:
                z_count = 0
                z_pct = 0.0
                z_lower = mean
                z_upper = mean
                z_sample = []

            z_detail = OutlierDetectionDetail(
                method="Z-score (|z| > 3)",
                outlier_count=z_count,
                outlier_percentage=z_pct,
                lower_bound=round(z_lower, 4),
                upper_bound=round(z_upper, 4),
                sample_outliers=z_sample,
            )

            outliers_dict[col] = ColumnOutliers(iqr=iqr_detail, z_score=z_detail)

        return outliers_dict

    def _analyze_correlations(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> CorrelationAnalysis:
        """Compute Pearson correlation matrix and identify strongest correlation pairs."""
        if len(numeric_cols) < 2:
            return CorrelationAnalysis()

        corr_df = df[numeric_cols].corr()
        corr_matrix: dict[str, dict[str, float]] = {}
        for col in corr_df.columns:
            corr_matrix[col] = {
                target: round(float(val), 4) if pd.notna(val) else 0.0
                for target, val in corr_df[col].items()
            }

        pairs: list[CorrelationPair] = []
        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                col_a = numeric_cols[i]
                col_b = numeric_cols[j]
                val = corr_df.iloc[i, j]
                if pd.notna(val) and abs(val) >= 0.5:
                    if val >= 0.8:
                        strength = "strong_positive"
                    elif val >= 0.5:
                        strength = "moderate_positive"
                    elif val <= -0.8:
                        strength = "strong_negative"
                    else:
                        strength = "moderate_negative"

                    pairs.append(
                        CorrelationPair(
                            column_a=col_a,
                            column_b=col_b,
                            correlation=round(float(val), 4),
                            strength=strength,
                        )
                    )

        # Sort pairs by absolute correlation descending
        pairs.sort(key=lambda p: abs(p.correlation), reverse=True)

        top_pos = next((p for p in pairs if p.correlation > 0), None)
        top_neg = next((p for p in pairs if p.correlation < 0), None)

        return CorrelationAnalysis(
            correlation_matrix=corr_matrix,
            strongest_correlations=pairs[:10],
            top_positive=top_pos,
            top_negative=top_neg,
        )

    def _detect_trends(
        self,
        df: pd.DataFrame,
        datetime_cols: list[str],
        numeric_cols: list[str],
    ) -> TrendAnalysis:
        """Identify time-series trends: growth, decline, and seasonality patterns."""
        if not datetime_cols or not numeric_cols:
            return TrendAnalysis(has_time_series=False)

        date_col = datetime_cols[0]
        try:
            temp_df = df[[date_col] + numeric_cols].dropna(subset=[date_col]).copy()
            temp_df[date_col] = pd.to_datetime(temp_df[date_col])
            temp_df = temp_df.sort_values(by=date_col)
        except Exception as e:
            logger.warning("Failed to parse datetime column %s for trend analysis: %s", date_col, e)
            return TrendAnalysis(has_time_series=False)

        if len(temp_df) < 3:
            return TrendAnalysis(has_time_series=True, date_columns=datetime_cols)

        trend_patterns: list[TrendPattern] = []

        for metric in numeric_cols[:5]:  # Limit to top 5 numeric columns
            series = temp_df[metric].dropna()
            if len(series) < 3:
                continue

            first_val = float(series.iloc[: max(1, len(series) // 5)].mean())
            last_val = float(series.iloc[-max(1, len(series) // 5) :].mean())

            if first_val != 0:
                pct_change = round(((last_val - first_val) / abs(first_val)) * 100, 2)
            else:
                pct_change = 0.0

            # Seasonality / Cyclicality heuristic via autocorrelation
            seasonality = False
            if len(series) >= 14:
                try:
                    # Test lag-7 and lag-4 autocorrelation
                    autocorr = series.autocorr(lag=7)
                    if pd.notna(autocorr) and abs(autocorr) > 0.4:
                        seasonality = True
                except Exception:
                    pass

            if pct_change > 5.0:
                trend_type: TrendDirection = "growth"
                desc = f"{metric} exhibited a growth trend of {pct_change:+.1f}% across the timeline."
            elif pct_change < -5.0:
                trend_type = "decline"
                desc = f"{metric} exhibited a decline trend of {pct_change:.1f}% across the timeline."
            elif abs(pct_change) <= 5.0:
                trend_type = "stable"
                desc = f"{metric} remained relatively stable ({pct_change:+.1f}% variation)."
            else:
                trend_type = "fluctuating"
                desc = f"{metric} fluctuated over the timeline with net change of {pct_change:+.1f}%."

            if seasonality:
                desc += " Cyclical or seasonal patterns were detected."

            trend_patterns.append(
                TrendPattern(
                    metric_column=metric,
                    date_column=date_col,
                    trend_type=trend_type,
                    growth_rate_pct=pct_change,
                    seasonality_detected=seasonality,
                    description=desc,
                )
            )

        return TrendAnalysis(
            has_time_series=True,
            date_columns=datetime_cols,
            trends=trend_patterns,
        )

    def _analyze_categoricals(
        self, df: pd.DataFrame, categorical_cols: list[str]
    ) -> dict[str, CategoryDetail]:
        """Calculate frequency counts, top categories, and cardinality level."""
        cat_analysis: dict[str, CategoryDetail] = {}
        row_count = len(df)

        for col in categorical_cols[:15]:  # Limit to 15 columns for performance
            series = df[col].dropna().astype(str)
            nunique = int(series.nunique())

            if nunique <= 10:
                cardinality: CardinalityLevel = "low"
            elif row_count > 100 and nunique / row_count > 0.4:
                cardinality = "high"
            else:
                cardinality = "medium"

            val_counts = series.value_counts().head(5)
            top_cats = {str(k): int(v) for k, v in val_counts.items()}
            total_non_null = len(series)
            freq_dist = {
                str(k): round(float(v / total_non_null * 100), 2)
                for k, v in val_counts.items()
            } if total_non_null > 0 else {}

            cat_analysis[col] = CategoryDetail(
                unique_count=nunique,
                cardinality_level=cardinality,
                top_categories=top_cats,
                frequency_distribution=freq_dist,
            )

        return cat_analysis

    def _generate_business_insights(
        self,
        df: pd.DataFrame,
        summary: DatasetSummary,
        statistics: dict[str, NumericColumnStatistics],
        missing_values: MissingValuesAnalysis,
        distributions: dict[str, ColumnDistribution],
        outliers: dict[str, ColumnOutliers],
        correlations: CorrelationAnalysis,
        trends: TrendAnalysis,
        categorical_analysis: dict[str, CategoryDetail],
    ) -> list[BusinessInsight]:
        """Convert statistical findings into natural, executive-level business insights."""
        insights: list[BusinessInsight] = []

        # 1. Dataset Domain & Volume Overview
        insights.append(
            BusinessInsight(
                category="overview",
                title=f"{summary.business_domain} Profile",
                insight=(
                    f"Dataset identified as {summary.dataset_type.capitalize()} domain containing "
                    f"{summary.row_count:,} records across {summary.column_count} features "
                    f"({len(summary.numeric_columns)} numeric, {len(summary.categorical_columns)} categorical)."
                ),
                impact="medium",
            )
        )

        # 2. Key Metric Concentration / Distribution Insight
        for col, dist in distributions.items():
            if dist.distribution_type == "skewed" and col in statistics:
                stat = statistics[col]
                direction = "higher" if dist.skewness > 0 else "lower"
                insights.append(
                    BusinessInsight(
                        category="distribution",
                        title=f"{col.replace('_', ' ').title()} Concentration",
                        insight=(
                            f"{col} exhibits a heavily skewed distribution (mean: {stat.mean:,.2f} vs "
                            f"median: {stat.median:,.2f}), indicating volume is concentrated toward {direction} values."
                        ),
                        impact="high",
                    )
                )
                break  # Pick the primary skewed metric

        # 3. Categorical Pareto / Concentration Insight
        for col, cat_detail in categorical_analysis.items():
            if cat_detail.top_categories:
                top_name, top_count = next(iter(cat_detail.top_categories.items()))
                top_pct = cat_detail.frequency_distribution.get(top_name, 0.0)
                if top_pct >= 30.0:
                    insights.append(
                        BusinessInsight(
                            category="category_concentration",
                            title=f"Dominant Segment in {col.replace('_', ' ').title()}",
                            insight=(
                                f"'{top_name}' represents {top_pct:.1f}% of total entries in {col}, "
                                f"highlighting significant concentration in this segment."
                            ),
                            impact="high",
                        )
                    )
                    break

        # 4. Correlation & Driver Insight
        if correlations.top_positive:
            top = correlations.top_positive
            insights.append(
                BusinessInsight(
                    category="correlation",
                    title="Strong Metric Co-Movement",
                    insight=(
                        f"Strong positive correlation detected between '{top.column_a}' and '{top.column_b}' "
                        f"(r = {top.correlation:.2f}). Increases in {top.column_a} closely track increases in {top.column_b}."
                    ),
                    impact="high",
                )
            )

        if correlations.top_negative:
            neg = correlations.top_negative
            insights.append(
                BusinessInsight(
                    category="correlation",
                    title="Inverse Relationship Detected",
                    insight=(
                        f"Inverse correlation between '{neg.column_a}' and '{neg.column_b}' (r = {neg.correlation:.2f}). "
                        f"Optimizing {neg.column_a} may create downward pressure on {neg.column_b}."
                    ),
                    impact="medium",
                )
            )

        # 5. Outlier Risk Insight
        for col, outlier in outliers.items():
            if outlier.iqr.outlier_count > 0 and outlier.iqr.outlier_percentage >= 2.0:
                insights.append(
                    BusinessInsight(
                        category="anomaly",
                        title=f"Statistical Outliers in {col.replace('_', ' ').title()}",
                        insight=(
                            f"{outlier.iqr.outlier_count} records ({outlier.iqr.outlier_percentage:.1f}%) in {col} "
                            f"fall beyond standard thresholds (upper cutoff: {outlier.iqr.upper_bound}), "
                            f"representing high-impact outliers."
                        ),
                        impact="high",
                    )
                )
                break

        # 6. Trend / Temporal Insight
        if trends.has_time_series and trends.trends:
            top_trend = trends.trends[0]
            insights.append(
                BusinessInsight(
                    category="trend",
                    title=f"Temporal Trend for {top_trend.metric_column.replace('_', ' ').title()}",
                    insight=top_trend.description,
                    impact="high" if top_trend.trend_type != "stable" else "medium",
                )
            )

        # 7. Data Quality & Missingness Warning
        if missing_values.total_missing_cells > 0:
            top_missing = max(
                missing_values.column_details.items(),
                key=lambda x: x[1].missing_percentage,
                default=None,
            )
            if top_missing:
                col, detail = top_missing
                insights.append(
                    BusinessInsight(
                        category="data_quality",
                        title="Missing Data Risk",
                        insight=(
                            f"{detail.missing_percentage:.1f}% missing values in column '{col}' "
                            f"({detail.missing_count:,} records). Imputation or cleaning is recommended before modeling."
                        ),
                        impact="medium" if detail.missing_percentage < 20 else "high",
                    )
                )

        return insights

    def _build_empty_eda_results(self, dataset_id: str | None) -> EDAResults:
        """Create a default response for empty datasets."""
        return EDAResults(
            dataset_summary=DatasetSummary(
                dataset_id=dataset_id,
                dataset_type="unknown",
                business_domain="Empty Dataset",
                row_count=0,
                column_count=0,
                column_names=[],
                numeric_columns=[],
                categorical_columns=[],
                datetime_columns=[],
                data_categories=[],
                memory_usage_mb=0.0,
                is_sampled=False,
            ),
            statistics={},
            missing_values=MissingValuesAnalysis(
                total_missing_cells=0,
                missing_percentage=0.0,
                affected_columns_count=0,
                affected_columns=[],
                column_details={},
            ),
            distributions={},
            outliers={},
            correlations=CorrelationAnalysis(),
            trends=TrendAnalysis(has_time_series=False),
            categorical_analysis={},
            business_insights=[
                BusinessInsight(
                    category="warning",
                    title="Empty Dataset",
                    insight="Dataset contains 0 records. Exploratory analysis cannot be performed.",
                    impact="high",
                )
            ],
        )


def get_eda_service(
    retrieval_service: DataRetrievalService = Depends(get_data_retrieval_service),
) -> EDAService:
    """FastAPI dependency provider for EDAService."""
    return EDAService(retrieval_service=retrieval_service)
