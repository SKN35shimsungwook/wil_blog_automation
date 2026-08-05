import code_files
from pathlib import Path
import tempfile, os

tmpdir = tempfile.mkdtemp()
paths = []
for i in range(6):
    p = os.path.join(tmpdir, f"big{i}.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write("print('x')\n" * 2000)  # 충분히 큰 파일
    paths.append(p)

ctx = code_files.extract_code_context(paths)
print("총 길이:", len(ctx))
print("MAX_TOTAL_CHARS:", code_files.MAX_TOTAL_CHARS)
assert len(ctx) <= code_files.MAX_TOTAL_CHARS + 500, f"길이 제한 초과: {len(ctx)}"
assert "생략" in ctx, "생략 표시 없음"
print("PASS: 총 길이 제한 정상 동작")

for p in paths:
    os.remove(p)
os.rmdir(tmpdir)
