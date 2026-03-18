# KF-QuickBudget

> 銀行・カードCSVを瞬時に分析して家計を見える化する。

## The Problem

家計簿が続かない。CSVをExcelで開いても集計が面倒。

## How It Works

1. 銀行/カードのCSV明細をアップロード
2. ヘッダー自動検出 + ユーザーによる列マッピング
3. DuckDBでSQL集計 + キーワードベースのカテゴリ自動分類
4. 月別・カテゴリ別のグラフ表示
5. 分析結果CSVをダウンロード

## Libraries Used

- **DuckDB** — インメモリSQL実行による高速集計
- **pandas** — データフレーム表示

## Development

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Hosted on [Hugging Face Spaces](https://huggingface.co/spaces/mitoi/kf-quick-budget).

---

Part of the [KaleidoFuture AI-Driven Development Research](https://kaleidofuture.com) — proving that everyday problems can be solved with existing libraries, no AI model required.
