(cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF'
diff --git a/src/models.py b/src/models.py
--- a/src/models.py
+++ b/src/models.py
@@ -0,0 +1,12 @@
+from dataclasses import dataclass
+from typing import Optional, List
+
+
+@dataclass
+class Article:
+    title: str
+    url: str
+    published_at: Optional[str]  # ISO 8601 string if available
+    summary: Optional[str]
+    images: List[str]
+
EOF
)
