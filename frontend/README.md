# Opencigan 프런트엔드

Svelte/Vite 기반 시간표 UI입니다. 백엔드·배포 전체 설명은 [루트 README](../README.md), 개발 절차는 [개발 가이드](../docs/development.md)를 참고하세요.

## 개발

```bash
npm ci
npm run dev
```

Vite가 표시하는 `/opensigan/` 주소로 접속합니다. 개발 중 `/api` 요청은 `http://127.0.0.1:8000`으로 프록시되므로 Python 백엔드를 별도로 시작해야 합니다.

```bash
npm run check
npm test
npm run build
```

`npm run dev`/`npm run build`는 먼저 `../docs/openapi.yaml`을 `public/openapi.yaml`에 복사합니다. 빌드 산출물은 `dist/`에 생성됩니다.

## 화면 기능

- 학교/학년/반 선택과 브라우저 로컬 저장
- **오늘**, **주간 반**, **학년 비교**, **교사 찾기**의 네 가지 시간표 보기
- 원본 변경 표시, 관측 이력 UI(서버 설정 시), 마지막 원본 갱신·수집 시각
- NEIS 급식 자동 매칭/동명이교 직접 확인, 날짜 선택과 같은 주의 결과 재사용
- 모바일 반응형 레이아웃, 테마 전환, 캐시된 응답 유지 및 갱신 실패 안내

PWA, 이미지/PDF 내보내기, 공유 링크, 외부 임베드는 **아직 로드맵 항목**입니다. [로드맵](../docs/roadmap.md).

## 배포에서 주의할 점

GitHub Pages 기본 경로는 `/opensigan/`입니다. GitHub Actions는 저장소 변수 `API_BASE_URL`을 `VITE_API_BASE_URL`로 전달합니다. 이 값을 빼고 `github.io`에 배포하면 데이터 API가 없다는 안내가 뜹니다. 별도 출처의 API를 쓰려면 백엔드 CORS도 일치해야 합니다.

API 문서 페이지는 `/opensigan/api-docs.html`, 정적 명세는 `/opensigan/openapi.yaml`입니다. 문서 내 Playground는 **같은 출처의 API가 있을 때만** 사용하며 `github.io`에서는 라이브 요청을 차단합니다.

디자인은 기존 Svelte 코드와 흑백 UI를 유지합니다. 디자인 키트의 가상 데이터나 캐릭터를 실제 서비스 콘텐츠로 사용하지 않습니다.
