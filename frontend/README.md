# 오픈시간표 프런트엔드

Node.js에서 `npm install` 후 `npm run dev`로 실행합니다. 개발 서버의 `/api` 요청은 `http://127.0.0.1:8000`으로 전달됩니다. 화면은 `/opensigan/` 경로에서 열립니다.

`npm run check`로 Svelte/TypeScript를 검사하고 `npm run build`로 `dist/` 정적 파일을 생성합니다. GitHub Pages 기본 경로는 `/opensigan/`입니다. 배포 빌드 시 `VITE_API_BASE_URL`에 API 서버 출처를 지정하세요. 설정하지 않으면 동일 출처 API를 사용하며, `github.io`에서는 설정 누락을 화면에 알립니다. 별도 출처의 API 서버는 브라우저 CORS를 허용해야 합니다.

급식 학교는 사용자가 NEIS 검색 결과에서 직접 선택하며, 선택은 시간표 학교별로 이 브라우저에 저장됩니다.
