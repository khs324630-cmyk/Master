# Market Crash Alert

다음 조건이 되면 휴대폰으로 [ntfy](https://ntfy.sh) 푸시 알림을 보냅니다.

| 조건 | 기본 기준 |
|---|---|
| S&P 500 지수가 전일 종가 대비 급락 | **-5% 이하** |
| CNN Fear & Greed Index | **20 이하** |

GitHub Actions가 자동으로 실행하므로 서버나 PC를 켜 둘 필요가 없습니다.

- 미국 장중(월~금)에는 15분마다 확인합니다.
- 그 외 시간에는 하루 2번 확인합니다(Fear & Greed용).
- 같은 조건은 하루(미국 동부시간 기준)에 한 번만 알립니다.

## 설정 방법

1. **ntfy 앱 설치**: Android(Play Store)나 iOS(App Store)에서 `ntfy`를 설치합니다.
2. **토픽 구독**: 앱에서 `+`를 누르고 남이 추측하기 어려운 토픽 이름을 입력합니다.
   예: `khs-market-alert-8f3k2q`
   ntfy.sh 토픽은 이름만 알면 누구나 구독하거나 보낼 수 있으니 길고 무작위로 정하세요.
3. **GitHub Secret 등록**: 저장소의 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `NTFY_TOPIC`
   - Value: 2번에서 정한 토픽 이름
4. **테스트**: **Actions → Market Alert → Run workflow**에서 `테스트 알림만 보내기`를 체크하고 실행합니다.
   휴대폰에 "테스트 알림"이 오면 설정이 끝난 것입니다.

## 기준 바꾸기 (선택)

**Settings → Secrets and variables → Actions → Variables** 탭에서 아래 변수를 추가합니다.

| Variable | 설명 | 기본값 |
|---|---|---|
| `DROP_THRESHOLD` | S&P 500 급락 기준(%) | `-5` |
| `FNG_THRESHOLD` | Fear & Greed 기준 | `20` |
| `NTFY_SERVER` | 자체 ntfy 서버 주소 | `https://ntfy.sh` |

비공개 토픽을 쓴다면 Secret에 `NTFY_TOKEN`을 추가합니다.

## 로컬 실행

```bash
NTFY_TOPIC=내토픽 python alert.py --dry-run   # 알림 없이 현재 값만 확인
NTFY_TOPIC=내토픽 python alert.py --test      # 테스트 알림
python -m unittest discover -s tests          # 테스트
```

외부 라이브러리 없이 Python 3.9 이상 표준 라이브러리만 사용합니다.

## 참고

- 데이터 출처는 Yahoo Finance(`^GSPC`)와 CNN Fear & Greed입니다. 둘 다 비공식 엔드포인트라 형식이 바뀌면 조회가 실패할 수 있습니다. 둘 다 실패하면 Actions 실행이 빨간색(실패)으로 표시됩니다.
- GitHub 정책상 저장소에 60일 동안 커밋이 없으면 예약 실행이 자동으로 꺼집니다. 그럴 때는 Actions 탭에서 다시 켜면 됩니다.
- GitHub 예약 실행은 부하에 따라 몇 분 늦게 시작될 수 있습니다.
