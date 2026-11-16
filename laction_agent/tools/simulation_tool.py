"""Bounded pure-data evolutionary what-if optimization. Not an execution sandbox."""
from __future__ import annotations

import json
import math
import random

from .registry import get_registry

reg = get_registry()


@reg.register(
    "evolve_plan",
    "Simulasi evolusi pilihan numerik di memori: evaluasi skenario, seleksi, crossover, mutasi. Tidak menjalankan kode atau menerapkan hasil; bukan sandbox HP.",
    {"type": "object", "properties": {
        "options": {"type": "array", "minItems": 1, "maxItems": 20, "description": "Satu angka benefits per skenario.", "items": {"type": "object", "properties": {"name": {"type": "string"}, "cost": {"type": "number"}, "benefits": {"type": "array", "items": {"type": "number"}}}, "required": ["name", "cost", "benefits"]}},
        "budget": {"type": "number", "description": "Batas total cost."},
        "population": {"type": "integer", "minimum": 4, "maximum": 64},
        "generations": {"type": "integer", "minimum": 1, "maximum": 10},
        "seed": {"type": "integer", "description": "Seed agar eksperimen dapat direproduksi."},
    }, "required": ["options", "budget"]},
)
def evolve_plan(options: list, budget: float, population: int = 24,
                generations: int = 5, seed: int = 0, context: dict | None = None) -> str:
    def number(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) <= 1_000_000 and math.isfinite(x)

    if (not isinstance(options, list) or not 1 <= len(options) <= 20 or
            not number(budget) or budget < 0 or
            type(population) is not int or not 4 <= population <= 64 or
            type(generations) is not int or not 1 <= generations <= 10 or
            type(seed) is not int or not -(2**63) <= seed < 2**63):
        return "ERROR: batas input/populasi/generasi/seed tidak valid."
    scenario_count = None
    clean = []
    names = set()
    for opt in options:
        if not isinstance(opt, dict):
            return "ERROR: setiap opsi harus objek."
        name, cost, benefits = opt.get("name"), opt.get("cost"), opt.get("benefits")
        if (not isinstance(name, str) or not name.strip() or len(name) > 80 or
                not name.isprintable() or name in names or not number(cost) or cost < 0 or
                not isinstance(benefits, list) or not 1 <= len(benefits) <= 10 or
                not all(number(x) for x in benefits)):
            return "ERROR: opsi harus memiliki name unik, cost nonnegatif, dan 1–10 benefits numerik terbatas."
        if scenario_count is None:
            scenario_count = len(benefits)
        if len(benefits) != scenario_count:
            return "ERROR: jumlah benefits setiap opsi harus sama."
        names.add(name)
        clean.append((name, cost, benefits))

    rng = random.Random(seed)
    n = len(clean)

    def evaluate(bits):
        cost = sum(opt[1] for bit, opt in zip(bits, clean) if bit)
        if cost > budget:
            return None
        totals = [sum(opt[2][i] for bit, opt in zip(bits, clean) if bit) for i in range(scenario_count)]
        return (min(totals), -cost, totals)

    # Empty portfolio is always feasible and survives elitism.
    zero = (0,) * n
    pool = [zero] + [tuple(rng.randrange(2) for _ in range(n)) for _ in range(population - 1)]
    history = []
    for _ in range(generations):
        valid = [(evaluate(bits), bits) for bits in pool]
        ranked = sorted(((score, bits) for score, bits in valid if score is not None), reverse=True)
        history.append(ranked[0][0][0])
        parents = [bits for _, bits in ranked[:max(2, population // 4)]]
        next_pool = [bits for _, bits in ranked[:2]]
        while len(next_pool) < population:
            a, b = rng.choice(parents), rng.choice(parents)
            child = [rng.choice((x, y)) for x, y in zip(a, b)]
            for i in range(n):
                if rng.random() < 1 / n:
                    child[i] = 1 - child[i]
            next_pool.append(tuple(child))
        pool = next_pool
    # Rank only evaluated generations, so history and selected result agree.
    score, bits = ranked[0]
    result = {
        "selected": [opt[0] for bit, opt in zip(bits, clean) if bit],
        "cost": -score[1], "scenario_totals": score[2], "worst_case_score": score[0],
        "best_by_generation": history, "seed": seed, "population": population,
        "generations": generations,
        "limitation": "Simulasi matematis berdasarkan angka input, bukan sandbox, digital twin, pelatihan model, atau bukti hasil dunia nyata; optimum tidak dijamin. Tidak ada aksi diterapkan.",
    }
    return json.dumps(result, ensure_ascii=False)


@reg.register(
    "simulate_files",
    "Dunia file virtual di memori: read/write/delete/list atas data yang diberikan saja. Tidak menjalankan shell atau APK, tidak menyentuh disk, dan bukan sandbox OS.",
    {"type": "object", "properties": {
        "files": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Peta path relatif ke isi teks; maksimal 40 file / 64 KiB."},
        "actions": {"type": "array", "maxItems": 50, "description": "Maks 50 operasi virtual.", "items": {"type": "object", "properties": {"op": {"type": "string", "enum": ["read", "write", "delete", "list"]}, "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["op"]}},
    }, "required": ["files", "actions"]},
)
def simulate_files(files: dict, actions: list, context: dict | None = None) -> str:
    from pathlib import PurePosixPath

    def valid_path(path):
        if not isinstance(path, str) or not path or len(path) > 200 or not path.isprintable() or "\\" in path:
            return False
        p = PurePosixPath(path)
        return not p.is_absolute() and all(part not in (".", "..") for part in path.split("/"))

    if not isinstance(files, dict) or len(files) > 40 or not isinstance(actions, list) or len(actions) > 50:
        return "ERROR: maksimal 40 file dan 50 operasi virtual."
    if any(not valid_path(k) or not isinstance(v, str) or len(v.encode("utf-8")) > 65536 for k, v in files.items()):
        return "ERROR: path/isi file virtual tidak valid."
    if sum(len(v.encode("utf-8")) for v in files.values()) > 65536:
        return "ERROR: total isi virtual dibatasi 64 KiB."
    world = dict(files)
    events = []
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("op") not in {"read", "write", "delete", "list"}:
            return f"ERROR pada langkah {index}: operasi tidak dikenal. Tidak ada aksi pada disk."
        op = action["op"]
        if op == "list":
            events.append({"op": "list", "paths": sorted(world)})
            continue
        path = action.get("path")
        if not valid_path(path):
            return f"ERROR pada langkah {index}: path virtual tidak valid. Tidak ada aksi pada disk."
        if op == "write":
            content = action.get("content")
            if not isinstance(content, str) or len(content.encode("utf-8")) > 65536:
                return f"ERROR pada langkah {index}: isi virtual tidak valid."
            world[path] = content
            if len(world) > 40 or sum(len(v.encode("utf-8")) for v in world.values()) > 65536:
                return f"ERROR pada langkah {index}: batas dunia virtual terlampaui. Tidak ada aksi pada disk."
            events.append({"op": op, "path": path, "bytes": len(content.encode("utf-8"))})
        elif op == "read":
            events.append({"op": op, "path": path, "exists": path in world, "content": world.get(path)})
        else:
            events.append({"op": op, "path": path, "existed": world.pop(path, None) is not None})
    return json.dumps({"events": events, "final_paths": sorted(world),
                       "notice": "Simulasi data in-memory saja; shell, APK, filesystem nyata, dan jaringan tidak dieksekusi."}, ensure_ascii=False)
