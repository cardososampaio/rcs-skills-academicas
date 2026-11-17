#!/usr/bin/env python3
"""Execute documented search plans and export reproducible academic corpora."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
from academic_core import VERSION
from academic_core.http import Client, atomic_json, now
from academic_core.model import canonical, deduplicate, eligibility, merge_records, normalize_text
from academic_core.sources import PRIMARY, SECONDARY, ALL_SOURCES, LENSES, SCOPES, search, crossref_record, openalex_record, doaj_record, s2_record, easyscielopack_record, attach, failure, openalex_id
from academic_core.exports import export_all
from academic_core.downloads import retrieve_pdfs

def load_records(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row.get("authors_json"):
                row["authors"] = json.loads(row["authors_json"])
            if row.get("editors_json"):
                row["editors"] = json.loads(row["editors_json"])
            for key in ("pdf_urls", "sources", "keywords", "themes", "countries", "issn", "isbn", "licenses", "notes", "missing_fields"):
                if row.get(key):
                    try:
                        row[key] = json.loads(row[key])
                    except ValueError:
                        row[key] = [row[key]]
            for target, src in (("source_ids", "source_ids_json"), ("metadata_by_source", "metadata_json"), ("citations_by_source", "citations_by_source_json"), ("provenance", "provenance_json"), ("metadata_conflicts", "metadata_conflicts_json"), ("affiliations", "affiliations_json")):
                row[target] = json.loads(row[src]) if row.get(src) else [] if target in ("provenance", "metadata_conflicts", "affiliations") else {}
            for key in ("is_oa", "retracted", "brazil_affiliation", "brazil_topic", "brazil_venue"):
                row[key] = True if row.get(key) in ("True", "true") else False if row.get(key) in ("False", "false") else None
        return rows
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if "results" in obj:
            return obj["results"]
        if "records" in obj:
            return obj["records"]
        if "data" in obj:
            return obj["data"]
        if "message" in obj and isinstance(obj["message"], dict):
            return obj["message"].get("items", [])
    raise ValueError("Input must contain an array of bibliographic records")

def validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object")
    if plan.get("mode", "simple") not in ("simple", "deep"):
        raise ValueError("mode must be simple or deep")
    config = plan.setdefault("config", {})
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    config.setdefault("types", ["article", "review"])
    config.setdefault("max_per_query", 60 if plan.get("mode") != "deep" else 200)
    config.setdefault("citation_style", "auto")
    if type(config["max_per_query"]) is not int or not 1 <= config["max_per_query"] <= 10000:
        raise ValueError("max_per_query must be between 1 and 10000")
    for key in ("year_start", "year_end"):
        if config.get(key) is not None and (type(config[key]) is not int or not 1400 <= config[key] <= 2200):
            raise ValueError(key + " must be a numeric publication year or null")
    if config.get("year_start") and config.get("year_end") and config["year_start"] > config["year_end"]:
        raise ValueError("year_start cannot exceed year_end")
    if config.get("citation_style") not in ("apa", "abnt", "auto"):
        raise ValueError("citation_style must be apa, abnt or auto")
    if config.get("openalex_scope") not in (None,) + SCOPES:
        raise ValueError("openalex_scope must be title_abstract or fulltext")
    for key in ("openalex_type_filter", "scielo_fallback"):
        if config.get(key) not in (None, True, False):
            raise ValueError(key + " must be true or false")
    languages = config.get("languages", [])
    if not isinstance(languages, list) or any(not isinstance(lang, str) or not re.fullmatch(r"[a-z]{2}", lang) for lang in languages):
        raise ValueError("Use a list of lowercase ISO two-letter language codes")
    if not isinstance(config["types"], list) or not config["types"] or any(not isinstance(t, str) or not t.strip() for t in config["types"]):
        raise ValueError("types must be a nonempty list of document types")
    queries, seen = plan.get("queries", []), set()
    if not isinstance(queries, list) or not queries:
        raise ValueError("At least one source-specific query is required")
    for q in queries:
        if not isinstance(q, dict):
            raise ValueError("Each query must be an object")
        if q.get("source") not in ALL_SOURCES or not str(q.get("query", "")).strip():
            raise ValueError("Each query needs a supported source and nonempty query string")
        if q["source"] == "bdtd" and not config.get("bdtd_requested"):
            raise ValueError("BDTD is opt-in. Set bdtd_requested only after an explicit user request")
        if (q.get("scope") or q.get("lens")) and q["source"] != "openalex":
            raise ValueError("scope and lens apply only to OpenAlex queries")
        if q.get("scope") not in (None,) + SCOPES:
            raise ValueError("scope must be title_abstract or fulltext")
        if q.get("lens") not in (None,) + tuple(LENSES):
            raise ValueError("lens must be one of " + ", ".join(LENSES))
        ident = (q["source"], q["query"], q.get("scope"), q.get("lens"))
        if ident in seen:
            raise ValueError("Duplicate source/query pair in plan")
        seen.add(ident)
    return plan

def read_config(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a JSON object")
    value = value.get("config", value)
    if not isinstance(value, dict):
        raise ValueError("config must be a JSON object")
    return value

def finalize(records, out, config, manifest):
    unique_records, probable = deduplicate(records)
    for r in unique_records:
        reasons = eligibility(r, config)
        if r["selection"] == "unassessed":
            # Unknown data needs verification, rather than automatic exclusion.
            uncertain = [x for x in reasons if x.endswith("unverified")]
            excluded = [x for x in reasons if x not in uncertain]
            r["selection"] = "outside_scope" if excluded else "needs_verification" if uncertain else "candidate"
            r["exclusion_reason"] = ", ".join(excluded)
        r["eligibility_checks"] = reasons
    manifest.update(unique_records=len(unique_records), input_records=len(records), probable_duplicates=len(probable),
                    candidates=sum(r["selection"] == "candidate" for r in unique_records),
                    outside_scope=sum(r["selection"] == "outside_scope" for r in unique_records), software_version=VERSION)
    atomic_json(Path(out) / "duplicatas_provaveis.json", probable)
    summary = export_all(unique_records, out, config, manifest)
    print(json.dumps(summary | {"output": str(out)}, ensure_ascii=False))
    return unique_records

def query_options(q):
    return {k: q[k] for k in ("scope", "lens") if q.get(k)}

def job_id(source, query, options=None, route=""):
    # Queries without options keep their original identifier, so earlier searches remain resumable.
    suffix = ("\0" + json.dumps(options, sort_keys=True) if options else "") + ("\0" + route if route else "")
    return hashlib.sha256((source + "\0" + query + suffix).encode()).hexdigest()[:20]

def record_job(state, client, job, result, event_start, checkpoint):
    # On retry, remove only records belonging to this job, then replace them.
    state["records"] = [r for r in state["records"] if r.get("search_job") != job]
    for r in result.records:
        r["search_job"] = job
        state["records"].append(r)
    state["jobs"][job] = result.manifest()
    state.setdefault("query_attempts", []).append({"job_id": job, **result.manifest()})
    state.setdefault("http_events", []).extend(client.events[event_start:])
    atomic_json(checkpoint, state)
    route = (result.options or {}).get("route", "")
    print(f"{result.source}{' (' + route + ')' if route else ''} {result.status} {len(result.records)} records", file=sys.stderr)

def scielo_route(jobs):
    direct = [j for j in jobs if j["source"] == "scielo"]
    if not direct:
        return "not_requested"
    indirect = any((j.get("options") or {}).get("route") == "scielo_indirect_via_openalex" and j["status"] in ("ok", "empty") for j in jobs)
    if all(j["status"] in ("ok", "empty") for j in direct):
        return "direct"
    return ("direct_partial_and_" if any(j["retrieved_count"] for j in direct) else "") + ("indirect_via_openalex" if indirect else "unavailable")

def run_search(args):
    if args.plan:
        plan = validate_plan(json.loads(Path(args.plan).read_text(encoding="utf-8-sig")))
    else:
        if not args.query:
            raise ValueError("Supply --plan or --query")
        sources = list(PRIMARY + SECONDARY) if args.stage == "all" else list(PRIMARY if args.stage == "primary" else SECONDARY)
        plan = validate_plan({"mode": args.mode, "config": {"languages": args.languages.split(",") if args.languages else [], "year_start": args.year_start, "year_end": args.year_end, "max_per_query": args.max_per_query or (200 if args.mode == "deep" else 60)}, "queries": [{"source": s, "query": args.query} for s in sources]})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    checkpoint = out / "checkpoint.json"
    state = {"plan_hash": signature, "started_at": now(), "jobs": {}, "records": [], "query_attempts": [], "http_events": []}
    if checkpoint.exists():
        if not args.resume:
            raise ValueError("An existing search is present. Use --resume for the same plan or choose a new output folder")
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        if state.get("plan_hash") != signature:
            raise ValueError("Resume requires exactly the same plan. Choose a new output folder for a revised search")
    atomic_json(out / "plano_executado.json", plan)
    client = Client(out, timeout=args.timeout, retries=1)
    order = {s: i for i, s in enumerate(ALL_SOURCES)}
    for q in sorted(plan["queries"], key=lambda x: order[x["source"]]):
        options = query_options(q)
        job = job_id(q["source"], q["query"], options)
        if job in state["jobs"] and state["jobs"][job]["status"] in ("ok", "empty"):
            continue
        event_start = len(client.events)
        result = search(client, q["source"], q["query"], plan["config"], options) if options else search(client, q["source"], q["query"], plan["config"])
        record_job(state, client, job, result, event_start, checkpoint)
        if q["source"] == "scielo" and result.status not in ("ok", "empty") and plan["config"].get("scielo_fallback") is not False:
            # The portal refused or broke off the search. Recover SciELO-listed journals through OpenAlex,
            # labelled as indirect. The portal job stays failed, so the limitation remains visible.
            route = "scielo_indirect_via_openalex"
            fallback = job_id("openalex", q["query"], {"lens": "scielo_listed"}, route)
            if not (fallback in state["jobs"] and state["jobs"][fallback]["status"] in ("ok", "empty")):
                event_start = len(client.events)
                indirect = search(client, "openalex", q["query"], plan["config"], {"lens": "scielo_listed", "provenance": {"route": route, "direct_search_failure": result.error or result.status}})
                record_job(state, client, fallback, indirect, event_start, checkpoint)
    manifest = {"plan": plan, "started_at": state["started_at"], "finished_at": now(), "queries": list(state["jobs"].values()),
                "scielo_route": scielo_route(list(state["jobs"].values())),
                "query_attempts": state.get("query_attempts", []), "http_events": state.get("http_events", []),
                "coverage_complete": all(j["complete"] for j in state["jobs"].values()), "limitations": [j for j in state["jobs"].values() if j["status"] not in ("ok", "empty") or j["truncated"]]}
    finalize(state["records"], out, plan["config"], manifest)
    return 0 if all(j["status"] in ("ok", "empty") for j in state["jobs"].values()) else 2

def run_import(args):
    records = load_records(args.input)
    mapper = {"openalex": openalex_record, "crossref": crossref_record, "doaj": doaj_record, "semantic_scholar": s2_record, "easy_scielo_pack": easyscielopack_record}.get(args.format)
    if args.format != "canonical" and mapper is None:
        raise ValueError("Unsupported input format")
    prepared = []
    source = args.source or ("scielo" if args.format == "easy_scielo_pack" else args.format if args.format != "canonical" else "")
    for raw in records:
        r = mapper(raw) if mapper else raw
        r = canonical(r)
        if source:
            r["sources"] = list(dict.fromkeys(r["sources"] + [source]))
            r["provenance"].append({"source": source, "method": "import", "format": args.format, "retrieved_at": now(), "skill_version": VERSION, "input_file": Path(args.input).name, "coverage": args.coverage})
            r.setdefault("metadata_by_source", {}).setdefault(source, []).append(raw)
        prepared.append(r)
    config = read_config(args.config) if args.config else {"citation_style": args.style, "languages": args.languages.split(",") if args.languages else [], "types": args.types.split(",")}
    finalize(prepared, args.out, config, {"method": "import", "input": Path(args.input).name, "source": source, "format": args.format, "coverage": args.coverage, "finished_at": now()})
    return 0

def run_enrich(args):
    records, checks = [canonical(r) for r in load_records(args.input)], []
    original_manifest = Path(args.input).parent / "manifesto_busca.json"
    original = json.loads(original_manifest.read_text(encoding="utf-8")) if original_manifest.exists() else {}
    config = read_config(args.config) if args.config else (original.get("plan") or {}).get("config", {})
    config = dict(config)
    if args.style != "auto" or not config.get("citation_style"):
        config["citation_style"] = args.style
    client = Client(args.out, timeout=args.timeout, retries=1)
    for r in records[:args.maximum]:
        if not r["doi"]:
            checks.append({"record_id": r["record_id"], "status": "no_doi", "next_action": "publisher_or_other_canonical_record"})
            continue
        response = client.get("https://api.crossref.org/works/" + quote(r["doi"], safe=""), {"mailto": os.getenv("CROSSREF_EMAIL")} if os.getenv("CROSSREF_EMAIL") else None)
        status, error = failure(response)
        if status:
            checks.append({"record_id": r["record_id"], "status": "unverified", "reason": error, "next_action": "check_registration_agency_or_publisher"})
            continue
        try:
            raw = response.json()["message"]
            alternative = attach(crossref_record(raw), "crossref", "DOI lookup", response, raw)
            similarity = SequenceMatcher(None, normalize_text(r["title"]), normalize_text(alternative["title"])).ratio()
            years_ok = r["year"] is None or alternative["year"] is None or abs(r["year"] - alternative["year"]) <= 1
            status = "needs_author_and_version_review" if similarity >= .90 and years_ok else "metadata_mismatch"
            checks.append({"record_id": r["record_id"], "status": status, "title_similarity": round(similarity, 4), "crossref_title": alternative["title"]})
            if status != "metadata_mismatch":
                enriched = merge_records(r, alternative)
                # Prefer structured author metadata only if names have been independently matched by the agent.
                r.clear()
                r.update(enriched)
        except (ValueError, TypeError, KeyError):
            checks.append({"record_id": r["record_id"], "status": "unverified", "reason": "invalid_crossref_response"})
            client.invalidate(response)
    atomic_json(Path(args.out) / "verificacao_referencias.json", checks)
    manifest = {"method": "DOI metadata enrichment", "input": Path(args.input).name, "finished_at": now(),
                "checked_records": len(checks), "check_limit": args.maximum, "check_limit_reached": len(records) > args.maximum,
                "original_manifest": original, "http_events": client.events, "config": config}
    export_all(records, args.out, config, manifest)
    print(json.dumps({"checked": len(checks), "output": args.out}))
    return 0

def run_merge(args):
    config = read_config(args.config) if args.config else {"citation_style": args.style, "types": args.types.split(",")}
    records = []
    for path in args.inputs:
        records.extend(load_records(path))
    finalize(records, args.out, config, {"method": "consolidation", "inputs": [Path(p).name for p in args.inputs], "finished_at": now(), "coverage": "see_original_search_manifests"})
    return 0

def run_citations(args):
    records = [canonical(r) for r in load_records(args.input)]
    config = dict(read_config(args.config)) if args.config else {"citation_style": args.style, "types": args.types.split(",")}
    config["max_per_query"] = args.max_per_seed
    seeds = [r for r in records if openalex_id(r)]
    relations = {"citing": ["cites"], "references": ["cited_by"], "both": ["cites", "cited_by"]}[args.direction]
    client = Client(args.out, timeout=args.timeout, retries=1)
    found, jobs = [], []
    for seed in seeds[:args.maximum_seeds]:
        for relation in relations:
            direction = "citing" if relation == "cites" else "references"
            result = search(client, "openalex", f"{relation}:{openalex_id(seed)}", config,
                            {"relation": (relation, openalex_id(seed)), "provenance": {"route": "citation_search", "direction": direction, "seed_record_id": seed["record_id"], "seed_title": seed["title"]}})
            found.extend(result.records)
            jobs.append(result.manifest() | {"seed_record_id": seed["record_id"], "direction": direction})
            print(f"{direction} {seed['record_id']} {result.status} {len(result.records)} records", file=sys.stderr)
    manifest = {"method": "citation search from seed documents", "input": Path(args.input).name, "direction": args.direction, "finished_at": now(),
                "queries": jobs, "seeds_searched": len(seeds[:args.maximum_seeds]), "seed_limit_reached": len(seeds) > args.maximum_seeds,
                "seeds_without_openalex_id": [r["record_id"] for r in records if not openalex_id(r)],
                "limitations": [j for j in jobs if j["status"] not in ("ok", "empty") or j["truncated"]], "http_events": client.events, "config": config}
    finalize(found, args.out, config, manifest)
    return 0 if all(j["status"] in ("ok", "empty") for j in jobs) else 2

def run_doctor(args):
    client = Client(args.out, timeout=args.timeout, retries=0)
    result = []
    for source in ALL_SOURCES if args.bdtd else PRIMARY + SECONDARY:
        response = search(client, source, "democracia", {"max_per_query": 1, "bdtd_requested": args.bdtd})
        result.append(response.manifest())
    # Report only whether each user-supplied credential is present. Values are never copied to the output.
    credentials = {name: "configured" if os.getenv(name) else "absent" for name in ("OPENALEX_API_KEY", "S2_API_KEY", "CROSSREF_EMAIL", "UNPAYWALL_EMAIL")}
    atomic_json(Path(args.out) / "diagnostico_bases.json", {"sources": result, "credentials": credentials})
    print(json.dumps([{k: row[k] for k in ("source", "status", "error", "retrieved_count")} | ({"quota": row["quota"]} if row.get("quota") else {}) for row in result], ensure_ascii=False))
    print(json.dumps({"credentials": credentials}), file=sys.stderr)
    if credentials["OPENALEX_API_KEY"] == "absent":
        print("OPENALEX_API_KEY absent: OpenAlex applies a small daily allowance shared by everyone on the same network address. "
              "Ask the user to create their own free key at https://openalex.org/settings/api and set it in their own environment.", file=sys.stderr)
    if any(row["source"] == "scielo" and row["status"] not in ("ok", "empty") for row in result):
        print("SciELO portal unavailable to this script: searches recover SciELO-listed journals through OpenAlex, labelled as indirect.", file=sys.stderr)
    return 0 if any(r["status"] in ("ok", "empty") for r in result) else 2

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("search", help="Run source-specific queries, primary sources before secondary sources")
    s.add_argument("--plan"); s.add_argument("--query"); s.add_argument("--out", required=True)
    s.add_argument("--mode", choices=("simple", "deep"), default="simple")
    s.add_argument("--stage", choices=("primary", "secondary", "all"), default="all")
    s.add_argument("--languages", default=""); s.add_argument("--year-start", type=int); s.add_argument("--year-end", type=int)
    s.add_argument("--max-per-query", type=int); s.add_argument("--resume", action="store_true"); s.add_argument("--timeout", type=int, default=20)
    s.set_defaults(func=run_search)
    i = sub.add_parser("import", help="Import records collected through connectors, browsing or database exports")
    i.add_argument("--input", required=True); i.add_argument("--out", required=True); i.add_argument("--source", default="")
    i.add_argument("--format", choices=("canonical", "openalex", "crossref", "doaj", "semantic_scholar", "easy_scielo_pack"), default="canonical")
    i.add_argument("--coverage", choices=("complete", "partial", "unknown"), default="unknown")
    i.add_argument("--config"); i.add_argument("--style", choices=("auto", "apa", "abnt"), default="auto")
    i.add_argument("--languages", default=""); i.add_argument("--types", default="article,review"); i.set_defaults(func=run_import)
    e = sub.add_parser("enrich", help="Crossref lookup, explicit metadata comparison and mismatch report")
    e.add_argument("--input", required=True); e.add_argument("--out", required=True); e.add_argument("--maximum", type=int, default=200)
    e.add_argument("--config")
    e.add_argument("--timeout", type=int, default=20); e.add_argument("--style", choices=("auto", "apa", "abnt"), default="auto"); e.set_defaults(func=run_enrich)
    m = sub.add_parser("merge", help="Consolidate API, plugin and curated records without dropping out-of-scope references")
    m.add_argument("--inputs", nargs="+", required=True); m.add_argument("--out", required=True); m.add_argument("--config")
    m.add_argument("--style", choices=("auto", "apa", "abnt"), default="auto"); m.add_argument("--types", default="article,review"); m.set_defaults(func=run_merge)
    c = sub.add_parser("citations", help="Find works citing the seed documents and works they reference, through OpenAlex")
    c.add_argument("--input", required=True); c.add_argument("--out", required=True)
    c.add_argument("--direction", choices=("citing", "references", "both"), default="both")
    c.add_argument("--maximum-seeds", type=int, default=20); c.add_argument("--max-per-seed", type=int, default=50)
    c.add_argument("--config"); c.add_argument("--style", choices=("auto", "apa", "abnt"), default="auto")
    c.add_argument("--types", default="article,review"); c.add_argument("--timeout", type=int, default=20); c.set_defaults(func=run_citations)
    d = sub.add_parser("doctor", help="Probe access and response schemas without interpreting failures as zero results")
    d.add_argument("--out", required=True); d.add_argument("--bdtd", action="store_true"); d.add_argument("--timeout", type=int, default=12); d.set_defaults(func=run_doctor)
    f = sub.add_parser("download", help="Optional PDF downloads, after the user's acceptance")
    f.add_argument("--input", required=True); f.add_argument("--out", required=True); f.add_argument("--approved", action="store_true"); f.add_argument("--maximum", type=int, default=20)
    f.set_defaults(func=lambda a: (retrieve_pdfs([canonical(r) for r in load_records(a.input)], Client(Path(a.out) / "requests"), a.out, a.approved, a.maximum), 0)[1])
    return p

def main():
    args = parser().parse_args()
    try:
        return args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
