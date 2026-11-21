# 모음 실시간 연결

Figma Starter 파일의 편집 내용을 플러그인 API로 읽어 모음 서버로 전송합니다. Figma REST API를 호출하지 않습니다.

전체 설치/배포/연결 방법은 [docs/figma-live-plugin.md](../docs/figma-live-plugin.md)에 있습니다.

Figma Desktop의 **Plugins → Development → New plugin → Figma design → Custom UI**로 먼저 플러그인 ID를 발급받고, `install.ps1 -Destination "생성된 manifest.json이 있는 폴더"`로 설치하세요. 이 폴더의 `manifest.json`은 ID가 없는 설정 템플릿입니다.

모음 대시보드에서 일회용 연결 코드를 만들고 플러그인에 현재 파일의 공유 링크와 함께 입력합니다. 최초 전송은 기준만 저장합니다. 이후 편집을 멈춘 뒤 약 1초 후 모음으로 보내며, 전송 완료 후 모음을 새로고침하면 변경사항이 나타납니다.

플러그인을 켜둔 동안만 동작합니다. 세션은 최대 8시간이며 새 연결 코드는 이전 세션을 교체합니다. 일반 플러그인은 현재 파일 키를 자동 조회할 수 없으므로, 프로젝트에 등록한 파일을 실제로 열었는지 확인하세요.

테스트: `node --test figma-plugin/tests/plugin.test.mjs` (백엔드 루트에서 실행).
