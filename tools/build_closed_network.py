# -*- coding: utf-8 -*-
"""폐쇄망(부대 PC)용 단일 HTML 생성기

index.html + vendor/ 를 HTML 파일 1개로 합친다.
 - 파일 더블클릭(file://) 실행: import/모듈 로드/로컬 파일 읽기 없이 동작
   (엔진 번들은 일반 script로, wasm·모델은 base64로 내장 → blob URL / 메모리 버퍼로 로드)
 - 외부 통신 차단: 엔진 사용 통계 전송 코드 무력화(vendor 번들 패치 확인) + CSP로 외부 연결 원천 차단
 - 부대 PC 속도 대응: 동시 인식 인원 2명 → 1명 (부대 PC 실측: 정밀 모델 2명 8fps, 1명 17fps)

사용: python3 tools/build_closed_network.py [출력파일]
"""
import base64, datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "vendor")
TODAY = datetime.date.today().strftime("%Y%m%d")
VERSION = "v6.5"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "팔굽혀펴기측정_%s_폐쇄망_%s.html" % (VERSION, TODAY))


def read(p, mode="r"):
    with open(os.path.join(V, p), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def b64(p):
    return base64.b64encode(read(p, "rb")).decode()


def script(js):
    return "<script>\n" + js.replace("</script", "<\\/script") + "\n</script>"


def replace_once(s, a, b):
    if s.count(a) != 1:
        raise SystemExit("치환 대상이 1곳이 아님(%d): %s" % (s.count(a), a[:80]))
    return s.replace(a, b)


html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()

# 1) 엔진 번들: ES 모듈 → 일반 script (export 를 전역 변수 대입으로)
bundle = read("mediapipe/vision_bundle.mjs")
if 'this.h=setInterval(()=>{this.flush()},6e4)' in bundle or "flush(t,e){this.i=[];t?.();return;" not in bundle:
    raise SystemExit("vendor 번들에 사용 통계 전송 차단 패치가 없음 (PR #4 적용 필요)")
bundle = re.sub(r"export\{[^}]*\};?", "window.MPV={FilesetResolver:ih,PoseLandmarker:Vc};", bundle)
bundle = re.sub(r"//# sourceMappingURL=\S+", "", bundle)
if re.search(r"(^|[;}\s])export[\s{]", bundle):
    raise SystemExit("번들에 export 가 남아 있음")

loader_js = read("mediapipe/wasm/vision_wasm_internal.js")
data_js = ("var CN_LOADER_JS=%s;\nvar CN_WASM_B64=\"%s\";\nvar CN_MODEL_B64=\"%s\";\n"
           % (json.dumps(loader_js), b64("mediapipe/wasm/vision_wasm_internal.wasm"), b64("mediapipe/pose_landmarker_full.task")))
helper_js = r"""
// [폐쇄망] base64 → 바이트, 엔진 파일을 메모리(blob)에서 불러옴 (file:// 에서도 동작)
function cnBytes(s) { var bin = atob(s), u = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; }
var cnFileset = null;
function cnGetFileset() {
    if (!cnFileset) cnFileset = {
        wasmLoaderPath: URL.createObjectURL(new Blob([CN_LOADER_JS], { type: "text/javascript" })),
        wasmBinaryPath: URL.createObjectURL(new Blob([cnBytes(CN_WASM_B64)], { type: "application/wasm" }))
    };
    return cnFileset;
}
// [폐쇄망] 오류를 화면에 표시 (교육생은 개발자 도구를 열 수 없음)
window.addEventListener("error", function(e) {
    var d = document.getElementById("cnErrorBox");
    if (!d) { d = document.createElement("div"); d.id = "cnErrorBox"; d.style.cssText = "position:fixed;left:8px;right:8px;bottom:8px;z-index:99999;background:#5a0f0f;color:#fff;border:2px solid #ff4444;padding:8px 12px;font:14px 'Malgun Gothic',sans-serif;white-space:pre-wrap"; document.body.appendChild(d); }
    d.textContent = "프로그램 오류: " + (e.message || e) + "\n화면을 사진으로 찍어 담당자에게 전달하십시오.";
});
"""

# 2) 외부 스크립트 → 내장
html = replace_once(html, '<script src="vendor/libs/camera_utils-0.3.1675466862.js"></script>', script(read("libs/camera_utils-0.3.1675466862.js")))
html = replace_once(html, '<script src="vendor/libs/mp4-muxer-5.1.4.js"></script>', script(read("libs/mp4-muxer-5.1.4.js")))

# 3) 엔진 로딩: 모듈 import·파일 경로 → 내장 데이터
html = replace_once(html, 'import(TASKS_VISION_URL + "/vision_bundle.mjs").then(function(vision) {\n            return vision.FilesetResolver.forVisionTasks(TASKS_VISION_URL + "/wasm").then(function(fileset) {',
                    'Promise.resolve(window.MPV).then(function(vision) {\n            return Promise.resolve(cnGetFileset()).then(function(fileset) {')
html = replace_once(html, 'baseOptions: { modelAssetPath: POSE_MODEL_URL, delegate: delegate },',
                    'baseOptions: { modelAssetBuffer: cnBytes(CN_MODEL_B64), delegate: delegate },')
html = replace_once(html, 'numPoses: 2,', 'numPoses: 1,   // [폐쇄망] 부대 PC 속도 (2명 8fps → 1명 17fps)')
html = replace_once(html, 'var TASKS_VISION_URL = new URL("vendor/mediapipe", document.baseURI).href;', 'var TASKS_VISION_URL = "";   // [폐쇄망] 엔진은 파일 안에 내장')
html = replace_once(html, 'var POSE_MODEL_URL = TASKS_VISION_URL + "/pose_landmarker_full.task";', 'var POSE_MODEL_URL = "";')

# 4) 외부 연결 원천 차단(CSP) + 머리 주석 + 버전 표시
csp = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
       "script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob:; worker-src blob:; connect-src blob: data:; "
       "img-src data: blob:; media-src blob: mediastream:; style-src 'unsafe-inline'; font-src data:\">")
header = ("<!--\n  육군 정자세 팔굽혀펴기 AI 정밀 측정체계 %s (폐쇄망판)\n  생성일: %s  (tools/build_closed_network.py 로 index.html 에서 생성 — 이 파일을 직접 고치지 말 것)\n"
          "  변경내역(폐쇄망판):\n   - 엔진·모델·라이브러리를 파일 안에 내장, 파일 더블클릭(file://) 실행\n"
          "   - 외부 통신 차단: 엔진 사용 통계 전송 무력화 + CSP(connect-src blob: data:)\n"
          "   - 동시 인식 인원 1명 (부대 PC 속도 대응). 채점자는 카메라 뒤·옆에 위치\n-->\n") % (VERSION, TODAY)
html = replace_once(html, "<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + header)
html = replace_once(html, '<meta charset="UTF-8">', '<meta charset="UTF-8">\n    ' + csp)
html = replace_once(html, '<div class="badge">검정 표준체계 v6.5</div>', '<div class="badge">검정 표준체계 v6.5 폐쇄망</div>')
html = replace_once(html, 'ctx.fillText(dateFormatted + "  v6.5 " + poseEngineTag', 'ctx.fillText(dateFormatted + "  v6.5폐쇄망 " + poseEngineTag')

# 4-1) 남은 통계 전송 주소 제거 (코드는 이미 무력화, 이중 안전장치) + 1명 인식 안내
bundle = replace_once(bundle, '"https://odml.pa.googleapis.com/v1/log"', '"data:,"')
html = replace_once(html, '<div class="setup-item" id="setupItemStill">⬜ 정지 유지</div>',
                    '<div class="setup-item" id="setupItemStill">⬜ 정지 유지</div>\n                    <div style="font-size:12px;color:#e5a93c;margin-top:4px">※ 폐쇄망판은 1명만 인식합니다. 채점자는 카메라 뒤나 옆에 서십시오.</div>')

# 5) 엔진·데이터 스크립트를 본 스크립트 앞에 삽입
html = replace_once(html, "\n<script>\n", "\n" + script(bundle) + "\n" + script(data_js) + "\n" + script(helper_js) + "\n<script>\n")

os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("생성:", OUT, "%.1fMB" % (os.path.getsize(OUT) / 1e6))
