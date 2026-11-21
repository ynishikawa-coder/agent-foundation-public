# 実物の会話ログの見本

見張り（plugin guard・session-watch）が読む会話ログの行の形を、作り物でなく実物で照らすための見本。

- `cloud_child_seeded.jsonl`: Claude Code v2.1.328 のクラウドの窓（別の窓が create_session で立てた窓）の会話ログの先頭
  から、頼みの行・仕組みの記録の行（attachment の remote_session_change）・道具の呼び出しと返り・返事の行を抜いた物。
  記録の欄（type・origin・promptSource・isMeta の有る無し・toolUseResult・isSidechain・entrypoint・usage）は実物のまま、
  文・id・path・model の名は作り物に置き換えた。

読み方の正本と、確かめた物（公式の文書・本体の判定）は `plugins/guard/scripts/guard_common.py` の `BASIS`。
Claude Code の版が変わって行の形が変わった時は、新しい版の窓の会話ログから同じ手で取り直す（文と id を作り物に置き換える）。
