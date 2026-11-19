# 変更の記録

記録は 1 PR に 1 つの file で `CHANGELOG.d/` に置く。この file には記録の行を書かない（書くと検査が赤）。書き方は `CHANGELOG.d/README.md`。

全部を新しい物が上で読む: `python3 scripts/changelog.py`（main に入った順に並べる）。断片へ移す前の記録（v0.4.1 から）は `CHANGELOG.d/00000000-断片へ移す前.txt` にそのまま在る。

v0.1.1 までの版は移す前の private の repo で出した（この repo には印を打たない・記録もここに持たない）。v0.2.0 の「足した」は、v0.1.1 の後・移す前に入った物。
