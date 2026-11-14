# Opencigan

[![CI](https://github.com/Transient-Onlooker/opensigan/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Transient-Onlooker/opensigan/actions/workflows/ci.yml)
[![Parser health](https://github.com/Transient-Onlooker/opensigan/actions/workflows/parser-health.yml/badge.svg?branch=main)](https://github.com/Transient-Onlooker/opensigan/actions/workflows/parser-health.yml)

**학교 시간표와 급식을 한곳에서 조회하는 웹서비스**입니다. 컴시간 시간표와 NEIS 급식을 사용합니다.

[웹사이트](https://opencigan.mcv.kr) · [API 명세](docs/openapi.yaml) · [기능 로드맵](docs/roadmap.md)

> **현재 상태 (2026-11-14):** 주 주소는 [opencigan.mcv.kr](https://opencigan.mcv.kr)입니다. 웹사이트는 Raspberry Pi 백엔드(Tailscale Funnel 경유)에 연결되어 시간표/급식 조회가 동작합니다. 외부 개발자용 API의 공개 운영은 별도 검증·승인이 필요합니다.

## 구현된 기능

- 학교 검색, 학년·반 선택, 선택 정보 브라우저 저장
- 오늘의 시간표, 우리 반 주간 시간표, 학년 전체 반별 비교, 교사별 시간표 검색
- 교시별 변경 표시, 원본 갱신/수집 시각, 실패 시 가능한 범위에서 이전 캐시 표시
- NEIS 학교 매칭 및 조식·중식·석식 조회, 날짜 이동
- 반응형 모바일 화면, 다크 모드
- 시간표 변경 이력 확인
- 읽기 전용 `/api/v1` JSON API 및 OpenAPI 3.1 명세
- 선택적 이용 통계와 인증을 요구하는 관리자 대시보드

## 문서

| 문서 | 내용 |
| --- | --- |
| [API 사용 가이드](docs/api-guide.md) | 엔드포인트, 응답 예시, 오류·캐시 의미 |
| [OpenAPI 3.1](docs/openapi.yaml) | 기계 판독 가능한 계약 |
| [개발 로드맵](docs/roadmap.md) | P0~P4 구현 현황 및 후속 작업 |
| [이용 통계](docs/analytics.md) | 설정, 집계 기준과 한계 |

## 라이선스

아직 별도의 `LICENSE` 파일이 없습니다. 공개 저장소라는 사실만으로 외부 사용·재배포 권한이 부여되지는 않습니다.
