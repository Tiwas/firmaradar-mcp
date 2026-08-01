import importlib.util
from pathlib import Path


def test_chatgpt_submission_preflight_passes():
    script = Path(__file__).resolve().parents[2] / "submission" / "preflight_submission.py"
    spec = importlib.util.spec_from_file_location("submission_preflight", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    submission = module.json.loads(module.SUBMISSION_PATH.read_text(encoding="utf-8"))
    module.validate(submission)
