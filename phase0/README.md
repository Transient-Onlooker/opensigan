# Phase 0 로컬 스파이크

기획서의 Python Workers 후보를 검토하는 별도 실험이다. `src/worker.py`는 `pycomcigan` 공개 API의 import 및 호출 가능 여부만 검사하며 학교 검색, 시간표 조회, 외부 통신, 프로토콜 구현을 수행하지 않는다. 경과 시간은 요청 처리 중 import의 **벽시계 시간**이지 Workers CPU 사용량이나 전체 콜드스타트가 아니다. 실패 시 예외 종류만 반환한다.

## 재현 (PowerShell, 로컬만)

전제: Python 3.13, Node.js, uv와 패키지 저장소 접근. Cloudflare 계정·토큰은 이 로컬 실험에 필요하지 않다. 작업 디렉터리는 이 폴더이다. `uv`가 첫 실행 때 패키지와 런타임을 내려받을 수 있다. 환경에 따라 추가 네트워크 접근이 필요하다.

```powershell
$env:PYTHONUTF8 = '1'
$env:WRANGLER_SEND_METRICS = 'false'
uv sync --locked
.\.venv\Scripts\uv.exe run --locked pywrangler dev --local --ip 127.0.0.1 --port 8787
```

별도 셸에서:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/
```

`import_ok`가 true이고 두 callable이 true면 **로컬 Workers 런타임에서 import만** 통과다. false 또는 서버 시작 실패는 오류 종류와 실행 도구 버전을 기록한다. 서버를 종료한 뒤 다시 시작해 최초 요청과 후속 요청을 별도로 비교할 수 있으나, import 시간에는 번들 생성·isolate 시작이 포함되지 않는다. 1.4.2는 조사한 upstream master의 메타데이터와 일치하도록 지정한 실험 버전이며 최신판이라는 뜻이 아니다. `uv.lock`과 `pylock.toml`은 이번 해석 결과다. `npx`로 선택되는 Wrangler는 자동 갱신될 수 있으므로 실제 버전도 기록해야 한다. Windows에서 `PYTHONUTF8=1`이 없으면 pywrangler가 가상환경 설정을 읽을 때 인코딩 오류가 발생할 수 있다.

`--remote`, 배포 및 Cloudflare 리소스 변경은 이 작업에 포함하지 않는다. 이 실험은 원본 포트 연결, 403/429, 타임아웃, 파싱 정확도, CPU/메모리를 시험하지 않는다. 계정·자격 증명을 찾거나 출력하지 않는다. 기준 및 추가 검증 방법은 [REPORT.md](REPORT.md)를 참조한다.
