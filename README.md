# glasslite

Glass(Pickle)처럼 화면과 음성을 로컬에 기록하고, 그 기록을 **MCP로 Claude Code에 연결**하는 Python PoC입니다.

```
[화면 mss] ─dedupe─▶ shots/*.jpg ┐
[마이크/루프백] ─▶ faster-whisper ┴─▶ SQLite(FTS5 trigram) ─▶ MCP 서버 ─▶ Claude Code
                                                         └─▶ (선택) Claude API 요약/질의
```

## 설치
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[audio]'
```

## 사용
```bash
glasslite capture                  # 화면 10초 간격 + 음성 15초 청크. Ctrl+C로 종료
glasslite capture --no-audio       # 화면만
glasslite capture --loopback       # 마이크([me]) + 시스템 오디오([them]) 동시 기록
glasslite capture --summarize-every 30   # 30분마다 새 발화가 있으면 Claude API로 자동 요약 저장
glasslite devices                  # 오디오 장치 목록 + 루프백 후보 (--device 로 마이크 선택)
glasslite recent --minutes 30      # 타임라인 출력
```

### Claude Code 연동 (API 키 불필요)
```bash
claude mcp add glasslite -- glasslite mcp
```
또는 이 디렉터리에 있는 `.mcp.json`을 사용합니다. 이 경우 `glasslite`가 PATH에 있어야 합니다. venv를 쓴다면 `command`를 `/path/to/.venv/bin/glasslite`처럼 절대경로로 바꾸세요. Claude Code에서 "최근 30분 회의 요약해줘"처럼 요청하면 다음 도구를 호출합니다.

| 도구 | 설명 |
|---|---|
| `recent_activity(minutes)` | 최근 전사·스크린샷 타임라인 |
| `search_memory(query)` | 전문 검색 (한국어 부분 일치) |
| `get_screenshot(segment_id?)` | 스크린샷 이미지 반환 (Claude가 직접 봄) |
| `save_note(text)` | 요약·메모를 저장해 이후 검색 가능 |

### 독립 실행 (Claude API, `ANTHROPIC_API_KEY` 필요)
```bash
glasslite summarize --minutes 30
glasslite ask "방금 결정된 일정이 뭐였지?"
```

## 설정 (환경변수)
| 변수 | 기본값 | 설명 |
|---|---|---|
| `GLASSLITE_HOME` | `~/.glasslite` | DB와 스크린샷 저장 위치 |
| `GLASSLITE_SCREEN_INTERVAL` | 10 | 캡처 간격(초) |
| `GLASSLITE_SCREEN_DIFF` | 0.02 | 이 비율 미만으로 바뀐 프레임은 버림 |
| `GLASSLITE_AUDIO_CHUNK` | 15 | 전사 단위(초) |
| `GLASSLITE_WHISPER_MODEL` | small | tiny/base/small/medium/large-v3 |
| `GLASSLITE_WHISPER_LANG` | 자동 | `ko` 등 |
| `GLASSLITE_CLAUDE_MODEL` | claude-opus-5-5 | |
| `GLASSLITE_RETENTION_DAYS` | 7 | capture 시작 시 오래된 데이터 삭제 |

## 참고
- **상대방 음성까지 녹음하려면** 루프백 장치가 필요합니다. macOS는 BlackHole, Windows는 "스테레오 믹스"(Stereo Mix) 또는 VB-Cable, Linux는 PulseAudio/PipeWire monitor를 씁니다. `--loopback`을 주면 이 장치를 이름으로 자동 감지합니다.
- **macOS 권한:** 터미널에 '화면 기록'과 '마이크' 권한을 줘야 합니다.
- **데이터 범위:** MCP 경로에서는 Claude Code가 조회한 내용만 Anthropic으로 전송됩니다. 캡처 자체는 로컬에서만 이루어집니다.
- **녹음 동의:** 녹음 시 참석자 동의와 관련 법규를 확인하세요.
