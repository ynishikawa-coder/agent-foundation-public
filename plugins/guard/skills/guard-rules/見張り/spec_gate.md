# spec_gate（設計書の型の gate を直に呼ぶ手）

- 出来事: PreToolUse
- する事: Bash の命令に設計書の型の gate `check_spec_doc.py` と `--lock` の両方が在れば止める（封の入口 `seal.py` は 15 §6 の決定照合が済むまで gate を呼ばない。直に呼ぶとその照合を飛ばせた）。AI の道具の呼び出しだけを止める（人の手の命令は止めない）。`--lock` の無い呼び出し（各 step の機械チェック・`--verify-receipt`・`--stamp`）は通す

## 止められた・知らされた時の直し方

spec-doc の入口から封をする: `python3 <spec-doc の skill の dir>/seal.py <設計書dir>`（照合だけなら `--match-only`）。照合で止まったら 15 §6 の行を直す（seal.py の直し方の文）

## 値の表の鍵

この見張りだけが読む鍵は無い（皆の鍵 `unattended_env`・`state_dir` は SKILL.md）。

## 射程の外

- 書くほどの穴は見つかっていない（見つけたら原因の台帳に行を足し、ここに書く）。
