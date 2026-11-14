# Opencigan 프런트엔드

Svelte와 Vite로 시간표, 급식, 설정 화면을 제공합니다. 처음 기여한다면 [개발 가이드](../docs/development.md)와 [기여 가이드](../CONTRIBUTING.md)를 참고하세요.

## 로컬 실행

`frontend/`에서 실행합니다.

```bash
npm ci
npm run dev
```

터미널에 표시된 주소(기본 `http://localhost:5173/`)를 엽니다. 개발 서버의 `/api` 요청은 `127.0.0.1:8000`으로 전달되므로 실제 데이터를 조회하려면 Python 백엔드도 실행해야 합니다.

## 검사

```bash
npm run check
npm test
npx playwright install chromium webkit
npx playwright test
```

Playwright는 배포용 화면을 빌드한 뒤 합성 데이터로 학급 전환, 저장, 공유 등 주요 흐름을 검사합니다. 실제 학교 데이터나 NEIS 키가 필요하지 않습니다.

## 빌드와 배포

`npm run build`의 결과는 `dist/`에 생성됩니다. 개발 서버와 빌드 모두 [OpenAPI 명세](../docs/openapi.yaml)를 정적 문서에 복사합니다. API 문서 경로는 `/api-docs.html`, 명세 경로는 `/openapi.yaml`입니다. 문서의 요청 실습은 같은 출처에 API가 있는 환경에서 사용할 수 있습니다.

GitHub Pages의 정적 화면은 저장소 변수 `API_BASE_URL`을 빌드 시 `VITE_API_BASE_URL`로 받습니다. 프런트엔드와 API의 출처가 다르면 [백엔드에서 프런트엔드 출처를 허용](../docs/operations.md)해야 합니다.
