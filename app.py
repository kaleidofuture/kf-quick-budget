"""KF-QuickBudget — Analyze bank/card CSV with DuckDB for quick budgeting."""

import streamlit as st

st.set_page_config(
    page_title="KF-QuickBudget",
    page_icon="\U0001F4B0",
    layout="wide",
)

from components.header import render_header
from components.footer import render_footer
from components.i18n import t

import io
import csv
import duckdb

# --- Header ---
render_header()
st.info("\U0001F4BB " + t("desktop_recommended"))

# --- Category classification rules ---
CATEGORY_RULES_JA = {
    "food": ["スーパー", "マルエツ", "イオン", "西友", "ライフ", "OK", "業務スーパー",
             "コンビニ", "セブン", "ローソン", "ファミリーマート", "食品", "弁当",
             "マクドナルド", "吉野家", "松屋", "すき家", "ガスト", "サイゼリヤ",
             "スターバックス", "ドトール", "カフェ", "レストラン", "居酒屋", "飲食"],
    "daily": ["Amazon", "楽天", "日用品", "ドラッグ", "マツキヨ", "ウエルシア",
              "ダイソー", "100均", "ホームセンター", "ニトリ", "無印"],
    "transport": ["JR", "鉄道", "バス", "Suica", "PASMO", "タクシー", "ガソリン",
                  "駐車", "高速", "ETC", "定期"],
    "utility": ["電気", "ガス", "水道", "通信", "携帯", "NTT", "au", "ソフトバンク",
                "楽天モバイル", "インターネット", "Wi-Fi", "NHK"],
    "medical": ["病院", "クリニック", "薬局", "医療", "歯科", "眼科", "保険"],
    "entertainment": ["映画", "ゲーム", "書籍", "本", "Netflix", "Spotify",
                      "YouTube", "Apple", "サブスク", "趣味"],
    "clothing": ["ユニクロ", "GU", "ZARA", "H&M", "服", "衣料", "靴", "アパレル"],
    "education": ["学費", "塾", "教材", "学校", "習い事", "セミナー"],
    "housing": ["家賃", "住宅", "管理費", "ローン", "修繕"],
    "debit": ["ID引落", "VISAデビット", "Jデビット", "即時引落", "デビット",
              "iD引落", "デビットカード", "VISA DEB", "J-Debit"],
    "other": [],
}

CATEGORY_NAMES_JA = {
    "food": "食費",
    "daily": "日用品",
    "transport": "交通費",
    "utility": "光熱・通信費",
    "medical": "医療費",
    "entertainment": "娯楽費",
    "clothing": "衣類",
    "education": "教育費",
    "housing": "住居費",
    "debit": "デビットカード",
    "other": "その他",
}

CATEGORY_NAMES_EN = {
    "food": "Food & Dining",
    "daily": "Daily Necessities",
    "transport": "Transportation",
    "utility": "Utilities & Telecom",
    "medical": "Medical",
    "entertainment": "Entertainment",
    "clothing": "Clothing",
    "education": "Education",
    "housing": "Housing",
    "debit": "Debit Card",
    "other": "Other",
}

# --- 3-category (simple) mode mapping ---
# housing + utility = fixed, everything else = variable
SIMPLE_CATEGORY_MAP = {
    "housing": "fixed",
    "utility": "fixed",
    "food": "variable",
    "daily": "variable",
    "transport": "variable",
    "medical": "variable",
    "entertainment": "variable",
    "clothing": "variable",
    "education": "variable",
    "debit": "variable",
    "other": "variable",
}

SIMPLE_CATEGORY_NAMES_JA = {
    "fixed": "固定費",
    "variable": "変動費",
    "savings": "貯蓄ポテンシャル",
}

SIMPLE_CATEGORY_NAMES_EN = {
    "fixed": "Fixed Costs",
    "variable": "Variable Costs",
    "savings": "Savings Potential",
}


def classify_category(description: str) -> str:
    """Classify a transaction description into a category."""
    desc_lower = description.lower() if description else ""
    for category, keywords in CATEGORY_RULES_JA.items():
        for keyword in keywords:
            if keyword.lower() in desc_lower:
                return category
    return "other"


def get_category_name(category_key: str, lang: str) -> str:
    """Get localized category name."""
    names = CATEGORY_NAMES_JA if lang == "ja" else CATEGORY_NAMES_EN
    return names.get(category_key, category_key)


def get_simple_category_name(simple_key: str, lang: str) -> str:
    """Get localized simple category name."""
    names = SIMPLE_CATEGORY_NAMES_JA if lang == "ja" else SIMPLE_CATEGORY_NAMES_EN
    return names.get(simple_key, simple_key)


def detect_columns(headers: list[str]) -> dict:
    """Auto-detect column roles from header names."""
    mapping = {"date": None, "description": None, "amount": None}

    date_keywords = ["日付", "date", "取引日", "利用日", "年月日", "決済日"]
    desc_keywords = ["摘要", "内容", "description", "明細", "利用先", "取引内容", "お支払先", "備考"]
    amount_keywords = ["金額", "amount", "出金", "支出", "お支払金額", "利用金額", "引落額"]

    for i, h in enumerate(headers):
        h_lower = h.strip().lower()
        if mapping["date"] is None:
            for kw in date_keywords:
                if kw.lower() in h_lower:
                    mapping["date"] = i
                    break
        if mapping["description"] is None:
            for kw in desc_keywords:
                if kw.lower() in h_lower:
                    mapping["description"] = i
                    break
        if mapping["amount"] is None:
            for kw in amount_keywords:
                if kw.lower() in h_lower:
                    mapping["amount"] = i
                    break

    return mapping


# --- Main Content ---
st.subheader(t("upload_title"))
st.caption(t("upload_help"))

# --- Mode toggle: detailed vs simple 3-category ---
mode = st.radio(
    t("mode_label"),
    ["detailed", "simple"],
    format_func=lambda m: t("mode_detailed") if m == "detailed" else t("mode_simple"),
    horizontal=True,
)

uploaded_file = st.file_uploader(t("upload_prompt"), type=["csv"])

if uploaded_file is not None:
    content = uploaded_file.read().decode("utf-8-sig", errors="replace")
    lines = content.strip().split("\n")

    if len(lines) < 2:
        st.error(t("empty_csv"))
    else:
        # Parse headers
        reader = csv.reader(io.StringIO(content))
        all_rows = list(reader)
        headers = all_rows[0]
        data_rows = all_rows[1:]

        # Auto-detect columns
        auto_mapping = detect_columns(headers)

        st.markdown(f"**{t('detected_columns')}** ({len(headers)} {t('columns')}, {len(data_rows)} {t('rows')})")

        # Let user override mapping
        col1, col2, col3 = st.columns(3)
        with col1:
            date_col = st.selectbox(
                t("date_column"),
                range(len(headers)),
                index=auto_mapping["date"] if auto_mapping["date"] is not None else 0,
                format_func=lambda i: headers[i],
            )
        with col2:
            desc_col = st.selectbox(
                t("desc_column"),
                range(len(headers)),
                index=auto_mapping["description"] if auto_mapping["description"] is not None else min(1, len(headers) - 1),
                format_func=lambda i: headers[i],
            )
        with col3:
            amount_col = st.selectbox(
                t("amount_column"),
                range(len(headers)),
                index=auto_mapping["amount"] if auto_mapping["amount"] is not None else min(2, len(headers) - 1),
                format_func=lambda i: headers[i],
            )

        # --- Budget setting per category ---
        st.markdown(f"### {t('budget_setting_title')}")
        st.caption(t("budget_setting_help"))

        budgets = {}
        if mode == "detailed":
            budget_cols = st.columns(4)
            cat_keys = [k for k in CATEGORY_NAMES_JA.keys()]
            for idx, cat_key in enumerate(cat_keys):
                lang = st.session_state.get("lang", "ja")
                cat_name = get_category_name(cat_key, lang)
                with budget_cols[idx % 4]:
                    val = st.number_input(
                        cat_name,
                        min_value=0,
                        value=0,
                        step=1000,
                        key=f"budget_{cat_key}",
                    )
                    if val > 0:
                        budgets[cat_key] = val
        else:
            budget_cols = st.columns(2)
            lang = st.session_state.get("lang", "ja")
            for idx, simple_key in enumerate(["fixed", "variable"]):
                sname = get_simple_category_name(simple_key, lang)
                with budget_cols[idx]:
                    val = st.number_input(
                        sname,
                        min_value=0,
                        value=0,
                        step=5000,
                        key=f"budget_simple_{simple_key}",
                    )
                    if val > 0:
                        budgets[simple_key] = val

        if st.button(t("analyze_button"), type="primary"):
            with st.spinner(t("processing")):
                # Build structured data
                transactions = []
                for row in data_rows:
                    if len(row) <= max(date_col, desc_col, amount_col):
                        continue
                    date_val = row[date_col].strip()
                    desc_val = row[desc_col].strip()
                    amount_str = row[amount_col].strip().replace(",", "").replace("\u00a5", "").replace("円", "").replace("-", "")

                    try:
                        amount_val = abs(float(amount_str))
                    except ValueError:
                        continue

                    category = classify_category(desc_val)
                    transactions.append({
                        "date": date_val,
                        "description": desc_val,
                        "amount": amount_val,
                        "category": category,
                    })

                if not transactions:
                    st.error(t("no_transactions"))
                else:
                    lang = st.session_state.get("lang", "ja")

                    # Use DuckDB for analysis
                    con = duckdb.connect(":memory:")
                    con.execute("""
                        CREATE TABLE txn (
                            date VARCHAR,
                            description VARCHAR,
                            amount DOUBLE,
                            category VARCHAR
                        )
                    """)
                    for txn in transactions:
                        con.execute(
                            "INSERT INTO txn VALUES (?, ?, ?, ?)",
                            [txn["date"], txn["description"], txn["amount"], txn["category"]],
                        )

                    st.success(t("analyzed").format(count=len(transactions)))

                    # --- Totals ---
                    total = con.execute("SELECT SUM(amount) FROM txn").fetchone()[0]

                    # --- Monthly data for MoM comparison ---
                    monthly_raw = con.execute("""
                        SELECT
                            CASE
                                WHEN date LIKE '____/__/__' THEN SUBSTRING(date, 1, 7)
                                WHEN date LIKE '____-__-__' THEN SUBSTRING(date, 1, 7)
                                WHEN date LIKE '____/__' THEN date
                                ELSE SUBSTRING(date, 1, 7)
                            END as month,
                            SUM(amount) as total
                        FROM txn
                        GROUP BY month
                        ORDER BY month
                    """).fetchall()

                    # --- Summary card (single screen overview) ---
                    st.markdown(f"### {t('summary_card_title')}")

                    cat_data = con.execute(
                        "SELECT category, SUM(amount) as total, COUNT(*) as cnt FROM txn GROUP BY category ORDER BY total DESC"
                    ).fetchall()

                    # Top 3 categories
                    top3 = cat_data[:3]
                    top3_text = "  /  ".join(
                        [f"**{get_category_name(c, lang)}** {amt:,.0f}" for c, amt, _ in top3]
                    )

                    # Month-over-month change
                    mom_text = ""
                    if len(monthly_raw) >= 2:
                        prev_month_name = monthly_raw[-2][0]
                        prev_total = monthly_raw[-2][1]
                        curr_month_name = monthly_raw[-1][0]
                        curr_total = monthly_raw[-1][1]
                        diff = curr_total - prev_total
                        sign = "+" if diff >= 0 else ""
                        pct_change = (diff / prev_total * 100) if prev_total > 0 else 0
                        mom_text = t("mom_change").format(
                            prev=prev_month_name, curr=curr_month_name,
                            diff=f"{sign}{diff:,.0f}", pct=f"{sign}{pct_change:.1f}"
                        )

                    summary_container = st.container(border=True)
                    with summary_container:
                        sc1, sc2 = st.columns([1, 2])
                        with sc1:
                            st.metric(t("total_spending"), f"{total:,.0f}")
                        with sc2:
                            st.markdown(f"**{t('top3_categories')}**")
                            st.markdown(top3_text)
                            if mom_text:
                                st.markdown(f"**{t('mom_label')}**: {mom_text}")

                    # ==============================================================
                    # DETAILED MODE
                    # ==============================================================
                    if mode == "detailed":
                        # --- Category breakdown ---
                        st.subheader(t("category_breakdown"))

                        chart_data = {}
                        for cat, cat_total, cnt in cat_data:
                            cat_name = get_category_name(cat, lang)
                            chart_data[cat_name] = cat_total

                        # Bar chart
                        import pandas as pd
                        df_chart = pd.DataFrame({
                            t("category_label"): list(chart_data.keys()),
                            t("amount_label"): list(chart_data.values()),
                        })
                        st.bar_chart(df_chart, x=t("category_label"), y=t("amount_label"))

                        # Category detail table with budget comparison
                        for cat, cat_total, cnt in cat_data:
                            cat_name = get_category_name(cat, lang)
                            pct = (cat_total / total * 100) if total > 0 else 0
                            line = f"**{cat_name}**: {cat_total:,.0f} ({pct:.1f}%) - {cnt}{t('transactions')}"

                            if cat in budgets and budgets[cat] > 0:
                                remaining = budgets[cat] - cat_total
                                if remaining >= 0:
                                    line += f"  \U00002705 {t('budget_remaining').format(amount=f'{remaining:,.0f}')}"
                                else:
                                    line += f"  \U0001F6A8 {t('budget_over').format(amount=f'{abs(remaining):,.0f}')}"

                            st.markdown(line)

                    # ==============================================================
                    # SIMPLE 3-CATEGORY MODE
                    # ==============================================================
                    else:
                        st.subheader(t("simple_breakdown_title"))

                        # Aggregate into fixed / variable
                        simple_totals = {"fixed": 0.0, "variable": 0.0}
                        simple_counts = {"fixed": 0, "variable": 0}
                        for cat, cat_total, cnt in cat_data:
                            skey = SIMPLE_CATEGORY_MAP.get(cat, "variable")
                            simple_totals[skey] += cat_total
                            simple_counts[skey] += cnt

                        # Savings potential = income unknown, so show as % hint
                        import pandas as pd
                        simple_chart_labels = []
                        simple_chart_values = []
                        for skey in ["fixed", "variable"]:
                            sname = get_simple_category_name(skey, lang)
                            simple_chart_labels.append(sname)
                            simple_chart_values.append(simple_totals[skey])

                        df_simple = pd.DataFrame({
                            t("category_label"): simple_chart_labels,
                            t("amount_label"): simple_chart_values,
                        })
                        st.bar_chart(df_simple, x=t("category_label"), y=t("amount_label"))

                        for skey in ["fixed", "variable"]:
                            sname = get_simple_category_name(skey, lang)
                            stotal = simple_totals[skey]
                            scnt = simple_counts[skey]
                            pct = (stotal / total * 100) if total > 0 else 0
                            line = f"**{sname}**: {stotal:,.0f} ({pct:.1f}%) - {scnt}{t('transactions')}"

                            if skey in budgets and budgets[skey] > 0:
                                remaining = budgets[skey] - stotal
                                if remaining >= 0:
                                    line += f"  \U00002705 {t('budget_remaining').format(amount=f'{remaining:,.0f}')}"
                                else:
                                    line += f"  \U0001F6A8 {t('budget_over').format(amount=f'{abs(remaining):,.0f}')}"

                            st.markdown(line)

                        # Savings potential tip
                        variable_pct = (simple_totals["variable"] / total * 100) if total > 0 else 0
                        if variable_pct > 60:
                            st.warning(t("savings_tip_high_variable").format(pct=f"{variable_pct:.0f}"))
                        elif variable_pct > 40:
                            st.info(t("savings_tip_moderate").format(pct=f"{variable_pct:.0f}"))
                        else:
                            st.success(t("savings_tip_good").format(pct=f"{variable_pct:.0f}"))

                        # Show which detailed categories map to which simple category
                        with st.expander(t("simple_detail_expander")):
                            for skey in ["fixed", "variable"]:
                                sname = get_simple_category_name(skey, lang)
                                mapped = [get_category_name(k, lang) for k, v in SIMPLE_CATEGORY_MAP.items() if v == skey]
                                st.markdown(f"**{sname}**: {', '.join(mapped)}")

                    # --- Monthly breakdown ---
                    st.subheader(t("monthly_breakdown"))

                    if monthly_raw:
                        import pandas as pd
                        df_monthly = pd.DataFrame(monthly_raw, columns=[t("month_label"), t("amount_label")])
                        st.bar_chart(df_monthly, x=t("month_label"), y=t("amount_label"))

                    # --- Download results ---
                    st.markdown("---")
                    result_rows = con.execute(
                        "SELECT date, description, amount, category FROM txn ORDER BY date"
                    ).fetchall()

                    csv_buffer = io.StringIO()
                    writer = csv.writer(csv_buffer)
                    if mode == "detailed":
                        writer.writerow(["date", "description", "amount", "category", "category_name"])
                        for row in result_rows:
                            writer.writerow(list(row) + [get_category_name(row[3], lang)])
                    else:
                        writer.writerow(["date", "description", "amount", "category", "category_name", "simple_category"])
                        for row in result_rows:
                            skey = SIMPLE_CATEGORY_MAP.get(row[3], "variable")
                            writer.writerow(list(row) + [get_category_name(row[3], lang), get_simple_category_name(skey, lang)])

                    st.download_button(
                        label=t("download_result"),
                        data=csv_buffer.getvalue(),
                        file_name="budget_analysis.csv",
                        mime="text/csv",
                    )

                    con.close()

else:
    st.info(t("no_file"))

# --- Footer ---
render_footer(libraries=["DuckDB"], repo_name="kf-quick-budget")
