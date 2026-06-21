import subprocess
def run_safe(args, timeout=5):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as e:
        class R: returncode=1; stdout=''; stderr=str(e)
        return R()
