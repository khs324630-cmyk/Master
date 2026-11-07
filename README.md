# 마켓 알림 (Market Crash Alert)

S&P 500이 **하루 5% 이상 급락**하거나 CNN **Fear & Greed Index가 20 이하**가 되면 아이폰으로 푸시 알림을 보내는 앱입니다.

- **아이폰 앱**: 홈 화면에 설치하는 웹앱(PWA)입니다. 자체 아이콘이 있고, 현재 지수와 최근 60일 추이를 보여 주며, 푸시 알림을 받습니다.
  App Store나 개발자 계정은 필요 없습니다. iOS 16.4 이상이면 됩니다.
- **감시 서버**: GitHub Actions가 미국 장중(월~금)에는 15분마다, 그 외 시간에는 하루 2번 확인하고 앱으로 푸시를 보냅니다. 무료이고 PC를 켜 둘 필요가 없습니다.
- **중복 방지**: 같은 조건은 한 번만 알립니다. S&P 500은 거래일마다, Fear & Greed는 하루마다입니다.

앱 주소: **https://khs324630-cmyk.github.io/Master/**

## 처음 설정 (한 번만)

### 1. GitHub Pages 켜기
저장소 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 바꿉니다.
그다음 **Actions → Market Alert → Run workflow**를 한 번 실행하면 앱 주소가 열립니다.

### 2. 아이폰에 앱 설치
1. 아이폰 **Safari**로 앱 주소를 엽니다.
2. 아래쪽 **공유 버튼(□↑) → 홈 화면에 추가**를 누릅니다.
3. 홈 화면의 **마켓 알림** 아이콘으로 앱을 엽니다. 반드시 Safari 탭이 아니라 홈 화면 아이콘으로 열어야 합니다.

### 3. 알림 연결
1. 앱에서 **알림 켜기 → 허용**을 누릅니다.
2. **연결 코드 복사**를 누릅니다.
3. 앱에 있는 **GitHub Secret 추가 페이지** 링크를 엽니다.
   직접 찾아가려면 Settings → Secrets and variables → Actions → New repository secret입니다.
   - Name: `PUSH_CONFIG`
   - Secret: 복사한 연결 코드
4. **Actions → Market Alert → Run workflow**에서 **테스트 알림 보내기**를 체크하고 실행합니다.
   아이폰에 "테스트 알림"이 오면 설정이 끝난 것입니다.

> 연결 코드에는 이 기기에 알림을 보낼 수 있는 키가 들어 있습니다. 비밀번호처럼 다루고 Secret에만 넣으세요.
> 여러 기기에서 받으려면 각 기기의 코드를 `[코드1, 코드2]`처럼 묶어서 넣습니다.
> 앱을 지웠다가 다시 설치하면 코드가 바뀌므로 다시 등록해야 합니다.

## 알림 기준 바꾸기

앱의 **알림 기준** 카드에서 고릅니다. 기준은 기기마다 따로 저장됩니다.

- S&P 500 하루 하락률: -1% ~ -10% (1% 단위)
- Fear & Greed 지수: 5 / 10 / 15 / 20 / 25 이하

알림은 GitHub Actions가 보내므로, 기준을 바꾼 뒤에는 **연결 코드 복사**를 다시 눌러 GitHub Secret `PUSH_CONFIG`를 새 코드로 바꿔야 적용됩니다.
앱에 노란 안내 문구가 떠 있으면 아직 바꾸지 않은 상태입니다.

ntfy 알림의 기준은 **Settings → Secrets and variables → Actions → Variables** 탭에서 아래 변수로 정합니다.

| Variable | 설명 | 기본값 |
|---|---|---|
| `DROP_THRESHOLD` | S&P 500 급락 기준(%) | `-5` |
| `FNG_THRESHOLD` | Fear & Greed 기준 | `20` |

## ntfy로도 받기 (선택)

Secret에 `NTFY_TOPIC`을 추가하면 ntfy 앱으로도 같은 알림이 갑니다. 안드로이드나 PC에서 받을 때 유용합니다.
비공개 토픽이면 `NTFY_TOKEN`을, 자체 서버면 Variable에 `NTFY_SERVER`를 추가합니다.

## 구조

```
alert.py                     시세 조회 · 조건 판단 · 웹 푸시/ntfy 발송 · data.json 생성
web/                         아이폰 웹앱 (index.html, app.js, sw.js, manifest, 아이콘)
.github/workflows/alert.yml   15분 주기 실행 + 웹앱 배포
tests/                       단위 테스트
```

로컬 실행:

```bash
pip install -r requirements.txt
python alert.py --dry-run --out web/data.json   # 알림 없이 현재 값 확인
python -m unittest discover -s tests
```

## 참고

- 데이터 출처는 Yahoo Finance(`^GSPC`)와 CNN Fear & Greed입니다. 둘 다 비공식 엔드포인트라 형식이 바뀌면 조회가 실패할 수 있습니다. 둘 다 실패하면 Actions 실행이 빨간색(실패)으로 표시됩니다.
- 푸시 키는 아이폰에서 직접 만들어지고, 저장되는 곳은 그 기기와 GitHub Secret뿐입니다.
- GitHub 정책상 저장소에 60일 동안 커밋이 없으면 예약 실행이 자동으로 꺼집니다. 그럴 때는 Actions 탭에서 다시 켜면 됩니다.
- GitHub 예약 실행은 몇 분 늦게 시작될 수 있습니다.
