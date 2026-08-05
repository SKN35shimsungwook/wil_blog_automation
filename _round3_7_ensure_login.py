import time
import tistory_browser

start = time.time()
ok = tistory_browser.ensure_login("tjddnrtla", on_status=print)
elapsed = time.time() - start
print("결과:", ok, "소요시간:", round(elapsed, 1), "초")
assert ok is True, "이미 로그인된 세션인데 실패함"
assert elapsed < 30, f"이미 로그인된 상태인데 너무 오래 걸림({elapsed}초) - 로그인 대기로 잘못 빠진 듯"
print("PASS: 기존 세션 재확인 정상")
