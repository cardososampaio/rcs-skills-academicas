"""Search routes, Brazilian lenses and traceability. Synthetic fixtures only, no network access."""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import academic_search as cli
from academic_core import VERSION
from academic_core.http import Client, Response, redacted_url
from academic_core.model import canonical
from academic_core.sources import search, SCIELO_INDIRECT_NOTE

def work(number=1):
    return {"id": f"https://openalex.org/W{number}", "title": f"Estudo sintético {number}", "publication_year": 2025, "type": "article",
            "language": "pt", "authorships": [{"author": {"display_name": "Ana Silva"}, "institutions": []}]}

def page(works, count=None, headers=None):
    body = json.dumps({"meta": {"count": len(works) if count is None else count}, "results": works}).encode()
    return Response(200, body, "application/json", headers, "https://api.openalex.org/works")

class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls, self.events = list(replies), [], []
    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append((url, dict(params or {}), headers))
        return self.replies.pop(0)

class OpenAlexQueryTests(unittest.TestCase):
    def test_default_search_is_limited_to_title_and_abstract(self):
        # Full-text matching returns a far noisier set, which would consume the per-query ceiling.
        client = FakeClient([page([work()])])
        result = search(client, "openalex", "democracia", {"max_per_query": 5})
        params = client.calls[0][1]
        self.assertEqual(params["search.title_and_abstract"], "democracia")
        self.assertNotIn("search", params)
        self.assertEqual(result.options["scope"], "title_abstract")
        self.assertEqual(result.records[0]["provenance"][0]["scope"], "title_abstract")

    def test_full_text_is_an_explicit_expansion(self):
        client = FakeClient([page([work()])])
        search(client, "openalex", "democracia", {"max_per_query": 5}, {"scope": "fulltext"})
        self.assertEqual(client.calls[0][1]["search"], "democracia")
        self.assertNotIn("search.title_and_abstract", client.calls[0][1])

    def test_document_types_are_filtered_by_the_source(self):
        client = FakeClient([page([work()])])
        search(client, "openalex", "q", {"max_per_query": 5, "types": ["article", "review"], "year_start": 2020})
        self.assertIn("type:article|review", client.calls[0][1]["filter"])
        self.assertIn("from_publication_date:2020-01-01", client.calls[0][1]["filter"])

    def test_type_filter_is_skipped_when_a_type_has_no_equivalent_or_is_disabled(self):
        for config in ({"types": ["article", "report"]}, {"types": ["article"], "openalex_type_filter": False}):
            client = FakeClient([page([work()])])
            search(client, "openalex", "q", {"max_per_query": 5, **config})
            self.assertNotIn("filter", client.calls[0][1])

    def test_brazilian_lens_is_a_labelled_filter(self):
        expected = {"br_venue": "primary_location.source.country_code:BR", "br_affiliation": "authorships.institutions.country_code:BR",
                    "scielo_listed": "primary_location.source.listed_in:scielo"}
        for lens, text in expected.items():
            client = FakeClient([page([work()])])
            result = search(client, "openalex", "digital democracy", {"max_per_query": 5}, {"lens": lens})
            self.assertIn(text, client.calls[0][1]["filter"])
            self.assertEqual(result.records[0]["provenance"][0]["lens"], lens)
            self.assertEqual(result.manifest()["options"]["lens"], lens)

    def test_lens_is_refused_outside_openalex(self):
        with self.assertRaisesRegex(ValueError, "only to OpenAlex"):
            search(FakeClient([]), "crossref", "q", {}, {"lens": "br_venue"})

    def test_user_key_comes_from_the_environment_and_is_redacted(self):
        client = FakeClient([page([work()])])
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "synthetic-value"}):
            search(client, "openalex", "q", {"max_per_query": 5})
        self.assertEqual(client.calls[0][1]["api_key"], "synthetic-value")
        self.assertNotIn("synthetic-value", redacted_url("https://api.openalex.org/works?api_key=synthetic-value&per_page=1"))

    def test_no_key_is_sent_when_the_user_has_none(self):
        client = FakeClient([page([work()])])
        with patch.dict(os.environ, {}, clear=True):
            search(client, "openalex", "q", {"max_per_query": 5})
        self.assertNotIn("api_key", client.calls[0][1])

    def test_remaining_allowance_is_reported(self):
        client = FakeClient([page([work()], headers={"X-RateLimit-Remaining-USD": "0.05", "X-RateLimit-Limit-USD": "0.1"})])
        result = search(client, "openalex", "q", {"max_per_query": 5})
        self.assertEqual(result.manifest()["quota"], {"remaining_usd": "0.05", "limit_usd": "0.1"})

class WorkflowRouteTests(unittest.TestCase):
    def invoke(self, args, client):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), patch.object(cli, "Client", return_value=client):
            namespace = cli.parser().parse_args(args)
            return namespace.func(namespace)

    def plan(self, root, config=None):
        path = Path(root) / "plan.json"
        path.write_text(json.dumps({"config": config or {}, "queries": [{"source": "scielo", "query": "democracia digital"}]}), encoding="utf-8")
        return path

    def test_blocked_scielo_is_recovered_indirectly_and_stays_reported_as_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([Response(403, b"<html>Establishing a secure connection ...</html>"), page([work(7)])])
            out = Path(tmp) / "out"
            code = self.invoke(["search", "--plan", str(self.plan(tmp)), "--out", str(out)], client)
            # The portal search did not happen, so the run is still incomplete.
            self.assertEqual(code, 2)
            self.assertIn("primary_location.source.listed_in:scielo", client.calls[1][1]["filter"])
            manifest = json.loads((out / "manifesto_busca.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scielo_route"], "indirect_via_openalex")
            self.assertEqual([q["status"] for q in manifest["queries"]], ["blocked", "ok"])
            rows = cli.load_records(out / "registros.json")
            self.assertEqual(rows[0]["sources"], ["openalex"])
            self.assertIn(SCIELO_INDIRECT_NOTE, rows[0]["notes"])
            self.assertEqual(rows[0]["provenance"][0]["route"], "scielo_indirect_via_openalex")

    def test_indirect_route_can_be_disabled_in_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([Response(403, b"Denied")])
            out = Path(tmp) / "out"
            self.assertEqual(self.invoke(["search", "--plan", str(self.plan(tmp, {"scielo_fallback": False})), "--out", str(out)], client), 2)
            self.assertEqual(len(client.calls), 1)
            manifest = json.loads((out / "manifesto_busca.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scielo_route"], "unavailable")

    def test_same_query_may_run_with_and_without_a_lens(self):
        plan = {"queries": [{"source": "openalex", "query": "q"}, {"source": "openalex", "query": "q", "lens": "br_venue"}]}
        self.assertEqual(len(cli.validate_plan(plan)["queries"]), 2)
        self.assertNotEqual(cli.job_id("openalex", "q"), cli.job_id("openalex", "q", {"lens": "br_venue"}))
        with self.assertRaisesRegex(ValueError, "only to OpenAlex"):
            cli.validate_plan({"queries": [{"source": "doaj", "query": "q", "lens": "br_venue"}]})
        with self.assertRaisesRegex(ValueError, "lens must be"):
            cli.validate_plan({"queries": [{"source": "openalex", "query": "q", "lens": "brazil"}]})

    def test_citation_search_records_seed_and_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            seeds = Path(tmp) / "seeds.json"
            seed = canonical({"title": "Semente sintética", "authors": [{"name": "Ana Silva"}], "year": 2020, "document_type": "article", "source_ids": {"openalex": "https://openalex.org/W123"}})
            other = canonical({"title": "Sem identificador", "authors": [{"name": "João Souza"}], "year": 2021, "document_type": "article"})
            seeds.write_text(json.dumps([seed, other], ensure_ascii=False), encoding="utf-8")
            client = FakeClient([page([work(8)]), page([work(9)])])
            out = Path(tmp) / "out"
            self.assertEqual(self.invoke(["citations", "--input", str(seeds), "--out", str(out)], client), 0)
            self.assertIn("cites:W123", client.calls[0][1]["filter"])
            self.assertIn("cited_by:W123", client.calls[1][1]["filter"])
            self.assertNotIn("search.title_and_abstract", client.calls[0][1])
            rows = cli.load_records(out / "registros.json")
            steps = {r["provenance"][0]["direction"]: r["provenance"][0] for r in rows}
            self.assertEqual(set(steps), {"citing", "references"})
            self.assertEqual(steps["citing"]["seed_record_id"], seed["record_id"])
            manifest = json.loads((out / "manifesto_busca.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["seeds_without_openalex_id"], [other["record_id"]])

class TraceabilityTests(unittest.TestCase):
    def test_csv_states_the_skill_version_and_the_query_date(self):
        # A later difference in results can then be attributed to the literature or to the procedure.
        with tempfile.TemporaryDirectory() as tmp:
            result = search(FakeClient([page([work()])]), "openalex", "q", {"max_per_query": 5})
            manual = canonical({"title": "Registro informado manualmente", "authors": [{"name": "Ana Silva"}], "year": 2024, "document_type": "article"})
            cli.export_all(result.records + [manual], tmp, {}, {"method": "synthetic"})
            with (Path(tmp) / "referencias.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = {row["title"]: row for row in csv.DictReader(handle)}
            found = rows["Estudo sintético 1"]
            self.assertEqual(found["skill_version"], VERSION)
            self.assertEqual(found["first_retrieved_at"], result.records[0]["provenance"][0]["retrieved_at"])
            # Unknown origin stays empty. The export date is not presented as a query date.
            self.assertEqual(rows["Registro informado manualmente"]["skill_version"], "")
            self.assertEqual(rows["Registro informado manualmente"]["first_retrieved_at"], "")
            manifest = json.loads((Path(tmp) / "manifesto_busca.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["software_version"], VERSION)
            self.assertTrue(manifest["exported_at"])
    def test_exported_paths_are_relative_to_the_output_folder(self):
        # Exported files are shared, so they must not carry the local user's folder (for example C:\Users\<name>).
        class Reply:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __init__(self):
                self.body = json.dumps({"meta": {"count": 1}, "results": [work()]}).encode()
            def read(self, n=-1):
                return self.body
            def geturl(self):
                return "https://api.openalex.org/works"
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        with tempfile.TemporaryDirectory() as tmp:
            client = Client(tmp, opener=lambda req, timeout: Reply())
            result = search(client, "openalex", "q", {"max_per_query": 5})
            raw_path = result.records[0]["provenance"][0]["raw_path"]
            self.assertTrue(raw_path.startswith("raw/"))
            self.assertTrue((Path(tmp) / raw_path).exists())
            # The folder name is checked both raw and JSON-escaped (backslashes doubled on Windows).
            leaks = {tmp, json.dumps(tmp)[1:-1]}
            for text in (json.dumps(result.records, ensure_ascii=False), json.dumps(result.manifest()), json.dumps(client.events)):
                for leak in leaks:
                    self.assertNotIn(leak, text)

if __name__ == "__main__":
    unittest.main()
