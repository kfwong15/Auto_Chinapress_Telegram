(cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF'
diff --git a/src/state_store.py b/src/state_store.py
--- a/src/state_store.py
+++ b/src/state_store.py
@@ -0,0 +1,45 @@
+import json
+import logging
+import os
+from typing import Set
+
+
+DEFAULT_STATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "seen.json"))
+
+
+class StateStore:
+    def __init__(self, path: str = DEFAULT_STATE_PATH) -> None:
+        self.path = path
+        os.makedirs(os.path.dirname(self.path), exist_ok=True)
+        self._seen: Set[str] = set()
+
+    def load(self) -> None:
+        if not os.path.exists(self.path):
+            self._seen = set()
+            return
+        try:
+            with open(self.path, "r", encoding="utf-8") as f:
+                data = json.load(f)
+            if isinstance(data, list):
+                self._seen = set(map(str, data))
+            elif isinstance(data, dict) and "seen" in data:
+                self._seen = set(map(str, data["seen"]))
+            else:
+                self._seen = set()
+        except Exception as e:
+            logging.warning("Failed to load state: %s", e)
+            self._seen = set()
+
+    def has(self, key: str) -> bool:
+        return key in self._seen
+
+    def add(self, key: str) -> None:
+        self._seen.add(key)
+
+    def save(self) -> None:
+        tmp_path = self.path + ".tmp"
+        with open(tmp_path, "w", encoding="utf-8") as f:
+            json.dump(sorted(self._seen), f, ensure_ascii=False, indent=2)
+        os.replace(tmp_path, self.path)
+
+
EOF
)
