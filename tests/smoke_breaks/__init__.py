"""入れて起動する試験（tests/test_plugin_smoke.py）の注入を 1 注入 1 file で持つ dir。

注入を足す PR は、この dir に <名>.py を 1 つ足すだけにする（ID・WANT・breaks(d) の 3 つを書く）。
試験の file の並びの末尾へ足す形では、並ぶ PR が同じ行へ足して続けて衝突した。
欠けた・壊れた注入の file は黙って飛ばさず、load() が名指しで止める（数えずに緑にしない）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(here: Path = HERE) -> list[tuple[str, str, object]]:
    """(ID, WANT, breaks) の並び（file の名の順）。形の崩れた file が 1 つでも在れば ValueError。"""
    out, errs, ids = [], [], set()
    for p in sorted(here.glob("*.py")):
        if p.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"smoke_breaks_{p.stem}", p)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
        except Exception as e:      # noqa: BLE001
            errs.append(f"{p.name}: 読めない（{e}）")
            continue
        i, w, b = getattr(m, "ID", None), getattr(m, "WANT", None), getattr(m, "breaks", None)
        if not (isinstance(i, str) and i and isinstance(w, str) and w and callable(b)):
            errs.append(f"{p.name}: ID・WANT（空でない字）と breaks(d) の 3 つが揃わない")
            continue
        if i in ids:
            errs.append(f"{p.name}: ID「{i}」が他の注入と重なる")
        ids.add(i)
        out.append((i, w, b))
    if errs or not out:
        raise ValueError("入れて起動する試験の注入の dir が崩れている: " + ("; ".join(errs) or "注入が 1 つも無い"))
    return out
