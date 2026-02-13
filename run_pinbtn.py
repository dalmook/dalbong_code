import os
import json
import time
import subprocess
from pathlib import Path

# ====== 여기만 수정 ======
TEMPLATE_PSD = r"C:\Users\chosu\OneDrive\문서\python\photoshop3\template.psd"
INPUT_DIR    = r"C:\Users\chosu\OneDrive\문서\python\photoshop3\INPUT"   # 이미지 11개 (01~11 추천)
OUTPUT_DIR   = r"C:\Users\chosu\OneDrive\문서\python\photoshop3\OUTPUT"
JSX_PATH     = r"C:\Users\chosu\OneDrive\문서\python\photoshop3\pinbtn_auto_fit.jsx"

SCALE_PERCENT = 20
OUTPUT_PREFIX = "PINBUTTON_"
COVER_MARGIN_PERCENT = 3

# 포토샵 exe 경로 (모르면 주석처리하고 COM만으로도 실행 시도함)
PHOTOSHOP_EXE = r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe"
# =======================

def write_config():
    temp = Path(os.environ.get("TEMP", "."))
    cfg_path = temp / "pinbtn_config.json"
    cfg = {
        "template_psd": TEMPLATE_PSD,
        "input_dir": INPUT_DIR,
        "output_dir": OUTPUT_DIR,
        "scale_percent": SCALE_PERCENT,
        "output_prefix": OUTPUT_PREFIX,
        "cover_margin_percent": COVER_MARGIN_PERCENT,
    }
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(cfg_path)

def ensure_photoshop_running():
    # Photoshop 실행 시도(이미 떠있으면 그냥 넘어가도 됨)
    if PHOTOSHOP_EXE and Path(PHOTOSHOP_EXE).exists():
        try:
            subprocess.Popen([PHOTOSHOP_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def run_jsx_via_com(jsx_path, wait_sec=60):
    # pywin32 필요: pip install pywin32
    import win32com.client

    t0 = time.time()
    while True:
        try:
            app = win32com.client.Dispatch("Photoshop.Application")
            break
        except Exception:
            if time.time() - t0 > wait_sec:
                raise RuntimeError("Photoshop COM 연결 실패. 포토샵이 설치/실행되어 있는지 확인해줘.")
            time.sleep(1)

    app.Visible = True
    # JSX 실행
    app.DoJavaScriptFile(jsx_path)

def main():
    cfg_path = write_config()
    print("Config written:", cfg_path)

    ensure_photoshop_running()
    run_jsx_via_com(JSX_PATH)
    print("Done.")

if __name__ == "__main__":
    main()
