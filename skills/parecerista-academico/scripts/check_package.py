#!/usr/bin/env python3
"""Confere distribuição completa; não avalia a qualidade de pareceres."""

import argparse
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True

REQUIRED = {
    "SKILL.md", "README.md", "CITATION.cff", "assets/casos-avaliacao.json",
    "scripts/check_package.py", "tests/test_package.py",
    "references/protocolo.md", "references/criterios-gerais.md",
    "references/quantitativa.md", "references/qualitativa.md",
    "references/metodos-mistos.md", "references/revisoes.md",
    "references/teoria.md", "references/estudos-caso.md",
    "references/texto-dados-ia.md", "references/internacionalizacao.md",
    "references/viabilidade.md", "references/saidas.md", "references/avaliacao.md",
}


def inspect(root):
    root = root.resolve()
    errors = []
    for name in sorted(REQUIRED):
        path = root / name
        if not path.is_file() or not path.stat().st_size:
            errors.append("Arquivo necessário ausente ou vazio: " + name)
    if errors:
        return errors
    main = (root / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"\A---\n(.*?)\n---\n", main, re.S)
    if not front:
        errors.append("Frontmatter ausente ou mal delimitado")
    else:
        header = front.group(1)
        for field in ("name", "description"):
            if not re.search(rf"^{field}:\s*\S", header, re.M):
                errors.append("Campo obrigatório ausente: " + field)
        if not re.search(r"^name: parecerista-academico$", header, re.M):
            errors.append("Nome incompatível com o pacote")
        version = re.search(r'^metadata:\n  version: "([0-9]+\.[0-9]+\.[0-9]+)"$', header, re.M)
        if not version:
            errors.append("Versão inválida")
        else:
            number = version.group(1)
            citation = (root / "CITATION.cff").read_text(encoding="utf-8")
            if f'version: "{number}"' not in citation:
                errors.append("Versão de citação diverge do núcleo")
            if number not in (root / "README.md").read_text(encoding="utf-8"):
                errors.append("README não informa a versão do núcleo")
    if len(main.splitlines()) > 500:
        errors.append("Núcleo excede 500 linhas")

    graph = {}
    for path in root.rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        graph[path.resolve()] = []
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            if re.match(r"(?:https?|mailto):", target) or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.is_relative_to(root):
                errors.append("Dependência fora do pacote: " + target)
            elif not resolved.exists():
                errors.append("Link quebrado: " + str(path.relative_to(root)) + " -> " + target)
            else:
                graph[path.resolve()].append(resolved)
    reachable, pending = set(), [(root / "SKILL.md").resolve()]
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        reachable.add(path)
        pending.extend(graph.get(path, []))
    for path in (root / "references").glob("*.md"):
        if path.resolve() not in reachable:
            errors.append("Referência sem rota a partir do núcleo: " + path.name)

    data = json.loads((root / "assets/casos-avaliacao.json").read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        errors.append("Casos devem ser uma lista não vazia")
        return errors
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            errors.append("Caso inválido")
            continue
        for field in ("id", "request", "material"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append("Campo de caso ausente ou inválido: " + field)
        case_id = case.get("id")
        if isinstance(case_id, str):
            if case_id in ids:
                errors.append("Identificador de caso repetido: " + case_id)
            ids.add(case_id)
        criteria = case.get("criteria")
        if not isinstance(criteria, list) or not criteria or not all(isinstance(x, str) and x.strip() for x in criteria):
            errors.append("Critérios devem ser lista de textos não vazios")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    tests_run = 0
    try:
        errors = inspect(args.root)
        if args.self_test and not errors:
            suite = unittest.defaultTestLoader.discover(str(args.root / "tests"), pattern="test_package.py")
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            tests_run = result.testsRun
            if not result.wasSuccessful():
                errors.append("Falha nos testes de integridade do pacote")
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    print(json.dumps({"passed": not errors, "errors": errors, "deterministic_tests_run": tests_run,
                      "behavioral_outputs_evaluated": False,
                      "scope": "Integridade de arquivos e metadados; não valida qualidade científica"}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
