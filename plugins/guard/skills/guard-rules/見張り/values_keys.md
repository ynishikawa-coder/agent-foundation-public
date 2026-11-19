# values_keys（値の表の知らない鍵）

- 出来事: PreToolUse・SessionStart
- する事: 使う側の repo の `config/skill-values.json` を Write・Edit・MultiEdit で書いた後に、土台が読まない鍵（土台が畳んだ・名を変えた鍵か書き違い）が残り、書く前より減っていなければ止める（AI の書き込みだけ・人の手は止めない）。起動の時に在れば知らせる。知っている鍵の正本は各 skill の SKILL.md の「repo ごとの値」の表と guard の値（照らすのは頭が土台の plugin の名か `common` の所だけ・`_` で始まる注は通す）

## 止められた・知らされた時の直し方

名指しされた鍵を消すか今の名の鍵へ移し、その repo の PR で直す。repo が自分で持つ値なら土台の plugin の名と `common` の外の頭へ移す。土台の道具が今も読む鍵なのに表に行が無いだけなら、土台の SKILL.md の表に行を足す PR を出す。手で照らす口: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/values_keys.py" config/skill-values.json`（知らない鍵が在れば exit 1）

## 値の表の鍵

この見張りだけが読む鍵は無い（皆の鍵 `unattended_env`・`state_dir` は SKILL.md）。

## 射程の外

- 値の表の知らない鍵の見張りは Write・Edit・MultiEdit だけを止める（Bash の書き換えは起動の時の知らせで拾う）。入れていない土台の plugin の頭は照らせない（手で回す口がその頭を名指す）。
