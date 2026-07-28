from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.chatbi import (
    build_chatbi_response,
    compile_safe_sql,
    is_chatbi_prompt,
    normalize_maas_intent,
    redact_prompt_for_maas,
    semantic_catalog,
)
from app.main import app
from app.metadata_center import build_metadata_center


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "cloud_real_bigdata" / "public_evidence" / "latest_e2e_result.json"


def sample_evidence() -> dict[str, object]:
    return {
        "available": True,
        "status": "success",
        "run_id": "test-chatbi-evidence",
        "generated_at": "2026-07-27T23:59:00Z",
        "gold_prefix": "obs://example/gold/",
        "gold_preview_rows": [
            {
                "year": "2025",
                "region": "Yucatan",
                "regime": "General",
                "resico_flag": False,
                "taxpayer_count": 10,
                "annual_income_total": 11916060,
                "annual_income_avg": 1191606,
            },
            {
                "year": "2025",
                "region": "Yucatan",
                "regime": "RESICO",
                "resico_flag": True,
                "taxpayer_count": 1,
                "annual_income_total": 2207936,
                "annual_income_avg": 2207936,
            },
            {
                "year": "2025",
                "region": "CDMX",
                "regime": "General",
                "resico_flag": False,
                "taxpayer_count": 5,
                "annual_income_total": 5000000,
                "annual_income_avg": 1000000,
            },
            {
                "year": "2025",
                "region": "Jalisco",
                "regime": "Persona Moral",
                "resico_flag": False,
                "taxpayer_count": 8,
                "annual_income_total": 4000000,
                "annual_income_avg": 500000,
            },
            {
                "year": "2025",
                "region": "Nuevo Leon",
                "regime": "RESICO",
                "resico_flag": True,
                "taxpayer_count": 2,
                "annual_income_total": 3000000,
                "annual_income_avg": 1500000,
            },
            {
                "year": "2025",
                "region": "Puebla",
                "regime": "RESICO",
                "resico_flag": True,
                "taxpayer_count": 2,
                "annual_income_total": 2000000,
                "annual_income_avg": 1000000,
            },
        ],
    }


class ChatBITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = sample_evidence()
        cls.previous_evidence = EVIDENCE_PATH.read_bytes() if EVIDENCE_PATH.exists() else None
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            json.dumps(cls.evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.previous_evidence is None:
            EVIDENCE_PATH.unlink(missing_ok=True)
        else:
            EVIDENCE_PATH.write_bytes(cls.previous_evidence)

    def test_engineering_prompt_stays_in_agent_workflow(self) -> None:
        self.assertFalse(
            is_chatbi_prompt("生成 PySpark、SQL 和 DataArts DAG，并部署到 MRS。")
        )
        self.assertFalse(is_chatbi_prompt("生成 PySpark 脚本并展示收入结果"))

    def test_generic_final_result_routes_to_chatbi(self) -> None:
        result = build_chatbi_response("我只想看最终的结果", self.evidence)

        self.assertTrue(result["handled"])
        self.assertEqual(result["kpis"][0]["value"], 28)

    def test_region_income_ranking_uses_gold_result(self) -> None:
        result = build_chatbi_response("2025 年各地区收入合计排名", self.evidence)
        self.assertTrue(result["handled"])
        self.assertTrue(result["available"])
        self.assertEqual(result["query_plan"]["group_by"], "region")
        self.assertEqual(result["table"]["rows"][0]["group"], "Yucatan")
        self.assertEqual(result["table"]["rows"][0]["annual_income_total"], 14123996.0)

    def test_english_locale_returns_fully_localized_report(self) -> None:
        result = build_chatbi_response(
            "Rank total annual income by region for 2025",
            self.evidence,
            locale="en",
        )

        self.assertTrue(result["handled"])
        self.assertIn("taxpayers match", result["answer"])
        self.assertEqual(result["kpis"][0]["label"], "Taxpayers")
        self.assertEqual(result["table"]["columns"][0]["label"], "Region")
        self.assertEqual(result["query_plan"]["filters"], ["Year=2025"])
        self.assertEqual(
            result["suggestions"][0],
            "Rank total annual income by region for 2025",
        )

    def test_api_accepts_english_locale(self) -> None:
        response = TestClient(app).post(
            "/api/chatbi/query",
            json={
                "prompt": "Rank total annual income by region for 2025",
                "history": [],
                "locale": "en",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["source"]["label"], "Published Huawei Cloud MRS Gold result")
        self.assertNotIn("纳税人", result["answer"])

    def test_english_tax_regime_comparison_groups_results(self) -> None:
        result = build_chatbi_response(
            "Compare taxpayer counts by tax regime",
            self.evidence,
            locale="en",
        )

        self.assertTrue(result["handled"])
        self.assertEqual(result["query_plan"]["group_by"], "regime")
        self.assertGreater(len(result["table"]["rows"]), 1)
        self.assertEqual(result["table"]["columns"][0]["label"], "Tax regime")

    def test_resico_count_returns_filtered_total(self) -> None:
        result = build_chatbi_response("2025 年 RESICO 纳税人数量是多少？", self.evidence)
        self.assertTrue(result["handled"])
        self.assertEqual(result["kpis"][0]["value"], 5)
        self.assertEqual(result["query_plan"]["filters"], ["年份=2025", "税制=RESICO"])

    def test_top_limit_does_not_change_summary_totals(self) -> None:
        result = build_chatbi_response("2025 年各地区收入合计 Top 1", self.evidence)

        self.assertEqual(len(result["table"]["rows"]), 1)
        self.assertEqual(result["kpis"][0]["value"], 28)
        self.assertEqual(result["kpis"][3]["value"], 5)

    def test_maas_intent_is_normalized_against_catalog(self) -> None:
        intent = normalize_maas_intent(
            {
                "intent": "query",
                "year": "2025",
                "region": "尤卡坦",
                "regime": "",
                "resico": None,
                "group_by": "",
                "metrics": ["annual_income_avg"],
                "primary_metric": "annual_income_avg",
                "limit": 10,
                "ascending": False,
                "confidence": 0.92,
                "clarification": "",
            },
            self.evidence,
        )

        self.assertEqual(intent["region"], "Yucatan")
        result = build_chatbi_response(
            "帮我看看尤卡坦的户均金额",
            self.evidence,
            intent_contract=intent,
            parser_trace={"mode": "maas", "used": True, "model": "glm-5.2"},
        )
        self.assertTrue(result["handled"])
        self.assertTrue(result["query_plan"]["maas_used"])
        self.assertEqual(result["query_plan"]["semantic_contract"]["region"], "Yucatan")

    def test_unknown_catalog_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_maas_intent(
                {
                    "intent": "query",
                    "year": "2025",
                    "region": "Atlantis",
                    "regime": "",
                    "resico": None,
                    "group_by": "region",
                    "metrics": ["taxpayer_count"],
                    "primary_metric": "taxpayer_count",
                    "limit": 10,
                    "ascending": False,
                    "confidence": 0.5,
                    "clarification": "",
                },
                self.evidence,
            )

    def test_compiler_uses_allowlisted_identifiers_and_parameters(self) -> None:
        compiled = compile_safe_sql(
            {
                "year": "2025",
                "region": "Yucatan'; DROP TABLE taxpayers; --",
                "regime": "",
                "resico": None,
                "group_by": "region",
                "metrics": ["annual_income_total"],
                "primary_metric": "annual_income_total",
                "limit": 5,
                "ascending": False,
            }
        )

        self.assertNotIn("DROP TABLE", compiled["sql"])
        self.assertEqual(compiled["parameters"]["region"], "Yucatan'; DROP TABLE taxpayers; --")
        self.assertTrue(compiled["read_only"])
        self.assertTrue(compiled["values_parameterized"])

    def test_maas_prompt_redacts_identifiers_and_secrets(self) -> None:
        redacted, changed = redact_prompt_for_maas(
            "查询 RFC ABCD900101XYZ，api_key=secret-value，Authorization Bearer token123"
        )

        self.assertTrue(changed)
        self.assertNotIn("ABCD900101XYZ", redacted)
        self.assertNotIn("secret-value", redacted)
        self.assertNotIn("token123", redacted)

    def test_catalog_contains_no_direct_identifiers(self) -> None:
        catalog = semantic_catalog(self.evidence)

        self.assertFalse(catalog["privacy"]["direct_identifiers_available"])
        self.assertNotIn("rfc", catalog["metrics"])

    def test_metadata_center_exposes_assets_schema_and_lineage(self) -> None:
        metadata = build_metadata_center(self.evidence)

        self.assertEqual(metadata["version"], "sat-metadata-center-v1")
        self.assertEqual(metadata["summary"]["asset_count"], 3)
        table = next(asset for asset in metadata["assets"] if asset["kind"] == "table")
        self.assertEqual(table["qualified_name"], "spark_catalog.tax_gold.taxpayer_regime_year")
        self.assertIn("taxpayer_count", {column["name"] for column in table["columns"]})
        self.assertGreaterEqual(len(metadata["lineage"]["edges"]), 4)

    def test_metadata_center_reports_verified_iceberg_snapshot(self) -> None:
        evidence = {
            **self.evidence,
            "iceberg": {
                "verified": True,
                "qualified_name": "spark_catalog.tax_gold.taxpayer_regime_year",
                "table_location": "obs://example/lakehouse/iceberg/sat/tax_gold/taxpayer_regime_year",
                "format_version": 2,
                "current_snapshot_id": "123",
                "snapshots": [
                    {
                        "snapshot_id": "123",
                        "committed_at": "2026-07-27 23:59:00",
                        "operation": "overwrite",
                        "total_records": "15",
                    }
                ],
            },
        }

        metadata = build_metadata_center(evidence)
        table = next(asset for asset in metadata["assets"] if asset["kind"] == "table")
        self.assertTrue(metadata["summary"]["iceberg_verified"])
        self.assertEqual(metadata["summary"]["snapshot_count"], 1)
        self.assertEqual(table["format"], "Apache Iceberg")
        self.assertEqual(table["properties"]["current_snapshot_id"], "123")

    def test_metadata_api_is_available(self) -> None:
        response = TestClient(app).get("/api/metadata/catalog")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "sat-metadata-center-v1")
        self.assertEqual(len(payload["assets"]), 3)

    def test_metadata_page_is_integrated_into_workbench(self) -> None:
        client = TestClient(app)
        home = client.get("/")
        metadata = client.get("/metadata")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(metadata.status_code, 200)
        self.assertIn('id="metadataView"', home.text)
        self.assertIn('role="tree"', metadata.text)
        self.assertIn("data-open-metadata", home.text)
        self.assertEqual(home.headers["cache-control"], "no-store, max-age=0")
        self.assertEqual(metadata.headers["cache-control"], "no-store, max-age=0")
        self.assertEqual(home.text, metadata.text)

    def test_api_uses_maas_for_unfamiliar_wording(self) -> None:
        class FakeMaaS:
            configured = True
            model = "glm-5.2"

            async def parse_chatbi_intent(self, prompt, catalog, history):
                return {
                    "intent": "query",
                    "year": "",
                    "region": "Yucatan",
                    "regime": "",
                    "resico": None,
                    "group_by": "",
                    "metrics": ["annual_income_avg"],
                    "primary_metric": "annual_income_avg",
                    "limit": 1,
                    "ascending": False,
                    "confidence": 0.94,
                    "clarification": "",
                }

        with patch("app.main.MaaSClient", return_value=FakeMaaS()):
            response = TestClient(app).post(
                "/api/chatbi/query",
                json={"prompt": "尤卡坦那边每户大概申报了多少钱？", "history": []},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["handled"])
        self.assertTrue(result["query_plan"]["maas_used"])
        self.assertEqual(result["query_plan"]["semantic_contract"]["region"], "Yucatan")
        self.assertTrue(result["query_plan"]["compiled_query"]["read_only"])

    def test_api_returns_clarification_when_maas_times_out(self) -> None:
        class FailingMaaS:
            configured = True
            model = "glm-5.2"

            async def parse_chatbi_intent(self, prompt, catalog, history):
                raise TimeoutError("simulated timeout")

        with patch("app.main.MaaSClient", return_value=FailingMaaS()):
            response = TestClient(app).post(
                "/api/chatbi/query",
                json={"prompt": "尤卡坦那边每户大概申报了多少钱？", "history": []},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["handled"])
        self.assertEqual(result["query_plan"]["semantic_parser"]["mode"], "local_fallback")
        self.assertEqual(result["query_plan"]["semantic_parser"]["error_type"], "TimeoutError")
        self.assertIn("安全映射", result["answer"])


if __name__ == "__main__":
    unittest.main()
