#!/usr/bin/env python3
"""Public release construction, receipt gating and handout export. No model calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile

from builders import BUILDERS, Build, write

REPO = Path(__file__).resolve().parents[1]
GATES = ["real_execution", "independent_reference", "clean_mixed_equivalence",
         "reset_repeatability", "dependency_intervention", "dependency_restoration",
         "decoy_noninterference", "rea_solvability", "no_leakage",
         "provenance_checked", "deduplicated"]
DENIED = {"private", "tests", "test", "reference", "references", "src", "source",
          "contract.md", "spec.json", "hidden.json", "cases.json"}
SOURCE_SUFFIXES = {".map", ".pdb", ".py", ".pyc", ".c", ".h", ".cs", ".java", ".ts", ".class", ".pem", ".key", ".p12", ".jks"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    write(Path(path), json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def relative(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Invalid relative path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name:
        raise ValueError("Invalid relative path: " + name)
    return Path(name)


def safe_file(root, name):
    path = root / relative(name)
    if not path.is_file() or root not in path.resolve().parents:
        raise ValueError("Missing or escaping file: " + name)
    current = root
    for part in relative(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink in file path: " + name)
    return path


def allowed(name):
    path = relative(name)
    if any(p.lower() in DENIED or p.lower().startswith("mutant") or p.lower().endswith(".dsym") for p in path.parts):
        raise ValueError("Private/source member in release: " + name)
    if path.suffix.lower() in SOURCE_SUFFIXES:
        raise ValueError("Source/debug/key member in release: " + name)


def inspect_file(path, name):
    allowed(name)
    if path.suffix.lower() in {".zip", ".apk", ".vsix"}:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                allowed(item.filename)
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Symlink in release archive")
                if Path(item.filename).suffix.lower() in {".zip", ".vsix", ".apk"}:
                    raise ValueError("Nested archive requires separate review")


def catalog():
    return load(REPO / "seeds/catalog.json")["seeds"]


def build(config_path, destination):
    config = load(config_path)
    seed = config["seed_id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]+", seed):
        raise ValueError("Invalid seed_id")
    track = config["track"]
    source = Path(config["source"]).expanduser().resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Source bundle must be a directory")
    destination = destination.resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Output and source must be disjoint")
    destination.mkdir(parents=True, exist_ok=False)
    inputs = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source bundle contains a symlink")
        if path.is_file():
            inputs[path.relative_to(source).as_posix()] = sha(path)
    files, commands = {}, []
    for condition in ["clean", "mixed"]:
        release = destination / condition
        release.mkdir()
        # Sources/logs stay outside the release directories.
        work = destination / "local-work" / condition
        work.mkdir(parents=True)
        b = Build(config, source, work, release)
        try:
            BUILDERS[track](b, condition == "mixed")
            b.resources()
        finally:
            dump(destination / "local-work" / (condition + "-commands.json"), b.logs)
        commands.extend(b.logs)
        files[condition] = {}
        for path in sorted(release.rglob("*")):
            if path.is_file():
                name = path.relative_to(destination).as_posix()
                safe_file(destination, name)
                inspect_file(path, name)
                files[condition][name] = sha(path)
        if not files[condition]:
            raise ValueError("Empty release")
    dump(destination / "build.json", {"schema": 1, "seed_id": seed, "track": track,
         "recipe": "portable-v5-export-1", "config_sha256": sha(config_path),
         "pipeline_sha256": {name: sha(REPO / "pipeline" / name) for name in ["run.py", "builders.py"]},
         "source_sha256": inputs, "files": files, "build_command_count": len(commands),
         "acceptance": "NOT_RUN", "perturbations": ["N", "S", "D"],
         "note": "Build success is not semantic equivalence or benchmark acceptance."})
    return verify(destination)


def verify(root):
    data = load(root / "build.json")
    if set(data["files"]) != {"clean", "mixed"}:
        raise ValueError("Both clean and mixed releases are required")
    count = 0
    for condition, files in data["files"].items():
        if not files:
            raise ValueError("Empty release file manifest")
        members = list((root / condition).rglob("*"))
        if (root / condition).is_symlink() or any(p.is_symlink() for p in members):
            raise ValueError("Symlink in release directory")
        actual = {p.relative_to(root).as_posix() for p in members if p.is_file()}
        if actual != set(files):
            raise ValueError("Release files differ from explicit manifest")
        for name, expected in files.items():
            if relative(name).parts[0] != condition:
                raise ValueError("Condition path mismatch")
            path = safe_file(root, name)
            inspect_file(path, name)
            if sha(path) != expected:
                raise ValueError("Stale artifact: " + name)
            count += 1
    return {"status": "HASH_VERIFIED", "files": count, "seed_id": data["seed_id"]}


def check_receipt(root, receipt):
    verify(root)
    data = load(receipt)
    if data.get("seed_id") != load(root / "build.json")["seed_id"] or data.get("build_sha256") != sha(root / "build.json"):
        raise ValueError("Receipt does not match this build")
    if any(data.get("checks", {}).get(gate) is not True for gate in GATES):
        raise ValueError("A required private acceptance gate is missing or failed")
    limits = {"public_inputs": 4, "hidden_inputs": 36, "test_families": 4, "semantic_mutants": 3}
    for key, limit in limits.items():
        if type(data.get(key)) is not int or data[key] < limit:
            raise ValueError("Insufficient acceptance coverage: " + key)
    if data.get("mutants_killed") != data["semantic_mutants"]:
        raise ValueError("Not all effective semantic mutants were detected")
    if not isinstance(data.get("evidence_sha256"), str) or not re.fullmatch("[0-9a-f]{64}", data["evidence_sha256"]):
        raise ValueError("Missing private evidence hash")
    return data


def validate(root, validator_config):
    verify(root)
    cfg = load(validator_config)
    receipt = root / "acceptance.json"
    if receipt.exists():
        raise FileExistsError("Do not overwrite an earlier acceptance receipt")
    argv = cfg["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("Validator argv must be a nonempty list of strings")
    if not any("{receipt}" in x for x in argv) or not any("{build}" in x for x in argv):
        raise ValueError("Validator must receive both build and receipt paths")
    argv = [x.replace("{build}", str(root)).replace("{receipt}", str(receipt)) for x in argv]
    subprocess.run(argv, check=True, timeout=cfg.get("timeout_seconds", 3600))
    check_receipt(root, receipt)
    return {"status": "PRIVATE_RECEIPT_ACCEPTED", "note": "Trusted local validator assertion, not an independent public audit."}


def freeze(root):
    check_receipt(root, root / "acceptance.json")
    path = root / "freeze.json"
    if path.exists():
        raise FileExistsError("Refusing to replace an existing freeze")
    dump(path, {"build_sha256": sha(root / "build.json"), "receipt_sha256": sha(root / "acceptance.json")})
    return {"status": "FROZEN"}


def export(root, condition, destination):
    frozen = load(root / "freeze.json")
    if frozen["build_sha256"] != sha(root / "build.json") or frozen["receipt_sha256"] != sha(root / "acceptance.json"):
        raise ValueError("Freeze mismatch")
    check_receipt(root, root / "acceptance.json")
    if destination.exists() or root == destination or root in destination.parents:
        raise ValueError("Export needs a new directory outside the build")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="handout-", dir=destination.parent))
    try:
        files = load(root / "build.json")["files"][condition]
        for name in files:
            output = stage / Path(name).relative_to(condition)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_file(root, name), output)
        dump(stage / "HANDOUT.json", {"condition": "REL-" + condition,
             "files": {str(Path(k).relative_to(condition)): v for k, v in files.items()}})
        stage.rename(destination)
    except Exception:
        shutil.rmtree(stage)
        raise
    return {"status": "EXPORTED", "file_count": len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("catalog")
    sub.add_parser("diversity")
    p = sub.add_parser("build"); p.add_argument("--config", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    for action in ["verify", "validate", "freeze", "export"]:
        p = sub.add_parser(action); p.add_argument("--build", type=Path, required=True)
        if action == "validate": p.add_argument("--validator-config", type=Path, required=True)
        if action == "export":
            p.add_argument("--condition", choices=["clean", "mixed"], required=True)
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "catalog": result = catalog()
    elif args.action == "diversity":
        rows = catalog()
        result = {"seeds": len(rows), "tracks": dict(Counter(x["track"] for x in rows)),
                  "families": dict(Counter(x["functional_group"] for x in rows)),
                  "public_inputs": sum(x["public"] for x in rows), "hidden_inputs": sum(x["hidden"] for x in rows),
                  "perturbations": sorted({p for x in rows for p in x["perturbations"]})}
    elif args.action == "build": result = build(args.config.resolve(), args.out)
    else:
        root = args.build.resolve(strict=True)
        if args.action == "verify": result = verify(root)
        elif args.action == "validate": result = validate(root, args.validator_config)
        elif args.action == "freeze": result = freeze(root)
        else: result = export(root, args.condition, args.out.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
