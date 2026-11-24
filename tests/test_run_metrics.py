from dossier import build_dossier
from engine import run_metrics_text, run_scripted_offline


def test_metrics_line_counts_calls_and_errors():
    run = run_scripted_offline("S01")
    text = run_metrics_text(run)
    assert f"{len(run.evidence)} tool calls" in text
    assert "elapsed not recorded" in text          # scripted engine path does not time itself
    run.elapsed_s = 12.34
    assert "elapsed 12.3 s" in run_metrics_text(run)


def test_old_runs_without_elapsed_still_load_and_render():
    run = run_scripted_offline("S01")
    data = run.model_dump(mode="json")
    data.pop("elapsed_s")
    from schemas import RunResult
    old = RunResult.model_validate(data)
    assert old.elapsed_s is None
    assert build_dossier(old)[:4] == b"%PDF"
