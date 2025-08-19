(cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF'
diff --git a/src/__init__.py b/src/__init__.py
--- a/src/__init__.py
+++ b/src/__init__.py
@@ -0,0 +1,3 @@
+# Package marker for src
+
+
EOF
)
