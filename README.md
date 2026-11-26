# 프로젝트PM 발행 현황판

블로그·홈페이지 발행 여부를 매시간 자동 확인해 비밀번호로 잠긴 페이지에 보여줍니다.

- 주소(예정): `https://pm-9ee2be.k-apts.co.kr`
- 확인 방식: 각 채널의 RSS·사이트맵을 읽어 날짜별 발행 여부 판정
- 보호 방식: StatiCrypt로 페이지 전체를 암호화(AES-256). 비밀번호 없이는 내용을 읽을 수 없음
- 실행: GitHub Actions가 매시 7분에 실행 → GitHub Pages에 배포

## 파일

| 파일 | 역할 |
|---|---|
| `channels.json` | 채널 목록, 발행 주기, 마감 시각, 확인 방법 |
| `build.py` | 피드 확인 후 `index.html` 생성 (표준 라이브러리만 사용) |
| `template.html` | 화면 디자인 |
| `.github/workflows/build.yml` | 매시간 실행, 암호화, 배포 |

## 처음 설정 (한 번만)

1. **저장소 만들기**: GitHub `mapcityne` 계정에 `pm-dashboard` 저장소(Public)를 만들고 이 폴더 내용을 올립니다.
   - 무료 요금제의 GitHub Pages는 공개 저장소만 됩니다. 공개되는 것은 코드와 채널 주소뿐이고, 현황판 내용은 배포 때만 만들어져 암호화된 채로 올라갑니다.
2. **시크릿 등록**: 저장소 Settings → Secrets and variables → Actions
   - Secrets → `PM_PASSWORD`: 현황판 비밀번호 (12자 이상 권장)
   - Secrets → `PM_SALT`: 16진수 32자. 터미널에서 `python -c "import secrets;print(secrets.token_hex(16))"`로 생성
   - Variables → `PM_DOMAIN`: `pm-9ee2be.k-apts.co.kr`
3. **Pages 켜기**: Settings → Pages → Source를 **GitHub Actions**로 선택
4. **가비아 DNS**: k-apts.co.kr DNS 관리 → 레코드 추가
   - 타입 `CNAME`, 호스트 `pm-9ee2be`, 값 `mapcityne.github.io.`
5. **도메인 연결**: Settings → Pages → Custom domain에 `pm-9ee2be.k-apts.co.kr` 입력 → DNS 확인 후 **Enforce HTTPS** 체크
6. **첫 실행**: Actions 탭 → "발행 현황판 갱신" → Run workflow

## 채널 바꾸기 (`channels.json`)

- `cycle`: `"daily"`(매일), `[0,2,4]`(월·수·금, 월=0 … 일=6), `"none"`(정기 발행 없음)
- `due`: 이 시각까지 글이 없으면 그날을 ‘누락’으로 표시 (`"10:00"`)
- `check.type`
  - `rss`: `url`에 RSS 주소
  - `site`: `sitemap`의 lastmod로 갱신일 확인, 없으면 `page`의 Last-Modified
  - `manual`: 자동 확인 없이 `note` 문구만 표시

## 판정 기준

| 표시 | 뜻 |
|---|---|
| ✓ 완료 | 그날 발행된 글이 피드에 있음 |
| ✕ 누락 | 발행 예정일인데 마감 시각이 지나도 글이 없음 |
| ◷ 대기 | 오늘 예정, 아직 마감 전 |
| ○ 예정 | 앞으로의 발행 예정일 |
| ? 기록 범위 밖 | 피드에 남은 글보다 오래된 날짜라 판정 불가 |
| ! 확인 실패 | 피드를 읽지 못함 |

## 참고

- 서브도메인 이름은 인증서 공개 기록에 남으므로 완전히 숨길 수는 없습니다. 실제 보호는 비밀번호가 담당합니다.
- 비밀번호를 바꾸면 다음 실행부터 새 비밀번호가 적용됩니다. 기존 ‘기억하기’ 상태는 무효가 됩니다.
- 로컬 미리보기: `python build.py --out build --sample` 후 `build/index.html` 열기
