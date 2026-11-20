# glasslite

Glass(Pickle)처럼 화면과 음성을 로컬에 기록하고, **Claude Code가 CLI와 Skill로 그 기록을 조회**하게 하는 Python PoC입니다. 별도 서버는 필요 없고, MCP 서버는 선택 사항입니다.

```
[화면 mss] ─dedupe─▶ shots/*.jpg ┐
[마이크 / 루프백] ─▶ faster-whisper ┴─▶ SQLite(FTS5) ─┬─▶ glasslite CLI ◀── Claude Code (Skill + Bash/Read)
                                                    ├─▶ notes/YYYY-MM-DD.md (선택, Grep/Read)
                                                    ├─▶ MCP 서버 (선택, Claude Desktop 등)
                                                    └─▶ Claude API 요약/질의 (선택)
```

## 설치
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[audio]'          # MCP까지 쓰려면 '.[audio,mcp]'
glasslite install-skill --allow    # ~/.claude/skills에 Skill 설치 + glasslite 명령 실행 허용
```
`--allow`는 `~/.claude/settings.json`의 `permissions.allow`에 `Bash(glasslite *)`를 추가해, Claude Code가 조회 명령을 실행할 때마다 승인을 묻지 않게 합니다. venv를 쓴다면 `glasslite`가 PATH에 있는 상태(venv 활성화 또는 `pipx install`)에서 Claude Code를 실행하세요.

## 기록
```bash
glasslite capture                          # 화면 10초 간격 + 마이크 15초 단위 전사. Ctrl+C로 종료
glasslite capture --loopback --export-md   # 상대방 음성([them])도 기록 + 날짜별 마크다운 저장
glasslite capture --summarize-every 30     # 30분마다 Claude API로 자동 요약 (ANTHROPIC_API_KEY 필요)
glasslite devices                          # 오디오 장치 목록 + 루프백 후보
```

## Claude Code에서 쓰기
설치한 뒤 Claude Code에 "방금 회의 요약해줘", "아까 견적 얘기 언제 했지?", "10분 전 화면 보여줘"처럼 말하면, Skill이 아래 명령을 골라 실행합니다.

| 명령 | 용도 |
|---|---|
| `glasslite recent --minutes 30` | 최근 타임라인 |
| `glasslite search "키워드"` | 전문 검색 (한국어 부분 일치) |
| `glasslite shot [id]` | 스크린샷 파일 경로 출력. Claude Code가 Read로 이미지를 직접 봅니다 |
| `glasslite note "요약"` | 요약을 저장해 나중에 검색 가능하게 함 |

`--export-md`를 켰다면 `~/.glasslite/notes/*.md`도 Grep/Read로 바로 읽을 수 있습니다.

### 선택: MCP 서버
Claude Desktop 같은 다른 MCP 클라이언트에서도 쓰려면 아래처럼 등록합니다.
```bash
pip install -e '.[mcp]'
```
```bash
claude mcp add glasslite -- glasslite mcp
```

### 선택: Claude API 직접 호출
```bash
glasslite summarize --minutes 30
glasslite ask "방금 결정된 일정이 뭐였지?"
```

## 설정 (환경변수)
| 변수 | 기본값 | 설명 |
|---|---|---|
| `GLASSLITE_HOME` | `~/.glasslite` | DB, 스크린샷, 노트 저장 위치 |
| `GLASSLITE_SCREEN_INTERVAL` | 10 | 캡처 간격(초) |
| `GLASSLITE_SCREEN_DIFF` | 0.02 | 이 비율 미만으로 바뀐 프레임은 버림 |
| `GLASSLITE_AUDIO_CHUNK` | 15 | 전사 단위(초) |
| `GLASSLITE_WHISPER_MODEL` | small | tiny/base/small/medium/large-v3 |
| `GLASSLITE_WHISPER_LANG` | 자동 | `ko` 등 |
| `GLASSLITE_CLAUDE_MODEL` | claude-opus-5-5 | |
| `GLASSLITE_RETENTION_DAYS` | 7 | capture 시작 시 오래된 데이터 삭제 (마크다운 노트는 유지) |

## 참고
- **상대방 음성까지 녹음하려면** 루프백 장치가 필요합니다. macOS는 BlackHole, Windows는 "스테레오 믹스"(Stereo Mix) 또는 VB-Cable, Linux는 PulseAudio/PipeWire monitor를 씁니다. `--loopback`을 주면 이 장치를 이름으로 자동 감지합니다.
- **macOS 권한:** 터미널에 '화면 기록'과 '마이크' 권한을 줘야 합니다.
- **데이터 범위:** 캡처는 로컬에서만 이루어집니다. Claude Code가 명령으로 조회한 내용만 Anthropic으로 전송됩니다.
- **녹음 동의:** 녹음 시 참석자 동의와 관련 법규를 확인하세요.
