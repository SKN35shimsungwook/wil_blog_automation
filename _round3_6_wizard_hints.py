import tkinter as tk
from setup_wizard import SetupWizard
import storage

def fit_geometry(win, w, h, **kw):
    win.geometry(f"{w}x{h}")

root = tk.Tk()
root.withdraw()
wiz = SetupWizard(root, storage.load_config(), fit_geometry)
wiz.update()
wiz._go_next()  # step 1: gemini

# 쿼터 초과 에러 시뮬레이션
wiz._on_gemini_test_done("error", "429 RESOURCE_EXHAUSTED. quota exceeded blah blah")
msg1 = wiz.gemini_test_status.get()
print("쿼터초과 메시지:", msg1)
assert "한도" in msg1, "쿼터초과 힌트 누락"

# 모델 폐기 에러 시뮬레이션
wiz._on_gemini_test_done("error", "404 NOT_FOUND. model no longer available")
msg2 = wiz.gemini_test_status.get()
print("모델폐기 메시지:", msg2)
assert "제공되지 않는" in msg2, "모델폐기 힌트 누락"

# 성공 케이스
wiz._on_gemini_test_done("ok", "pong")
msg3 = wiz.gemini_test_status.get()
print("성공 메시지:", msg3)
assert "정상 동작" in msg3

wiz.destroy()
root.destroy()
print("PASS: 마법사 에러 힌트 로직 전부 정상")
