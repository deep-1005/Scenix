path = "app/workers/tasks.py"
with open(path) as f:
    content = f.read()

with open(path + ".bak", "w") as f:
    f.write(content)

new_func = '''def _build_fastgs_cmd(scene_out: str, model_path: str) -> list:
    return [
        CONDA_PYTHON, FASTGS_TRAIN,
        "-s", scene_out,
        "--model_path", model_path,
        "--iterations", str(FASTGS_ITERATIONS),
        "--save_iterations", "15000", str(FASTGS_ITERATIONS),
        "--checkpoint_iterations", str(FASTGS_ITERATIONS),
        "-r", "2",
        "--densification_interval", "100",
        "--densify_until_iter", "15000",
        "--grad_abs_thresh", "0.0006",
        "--grad_thresh", "0.00015",
        "--loss_thresh", "0.06",
        "--highfeature_lr", "0.02",
        "--lambda_dssim", "0.3",
        "--lambda_opacity_reg", "0.01",
        "--lambda_scale_reg", "0.25",
        "--scale_reg_ratio", "5",
        "--reg_from_iter", "1500",
        "--test_iterations", "7000", "15000", "30000",
    ]


def _run_fastgs(db, job, scene_out: str):'''

old_func_start = "def _run_fastgs(db, job, scene_out: str):"
content = content.replace(old_func_start, new_func, 1)

old_inline_cmd = '''    cmd = [
        CONDA_PYTHON, FASTGS_TRAIN,
        "-s", scene_out,
        "--model_path", model_path,
        "--iterations", str(FASTGS_ITERATIONS),
        "--save_iterations", "15000", str(FASTGS_ITERATIONS),
        "--checkpoint_iterations", str(FASTGS_ITERATIONS),
        "-r", "2",
        "--densification_interval", "100",
        "--densify_until_iter", "15000",
        "--grad_abs_thresh", "0.0006",
        "--grad_thresh", "0.00015",
        "--loss_thresh", "0.06",
        "--highfeature_lr", "0.02",
        "--lambda_dssim", "0.3",
        "--lambda_opacity_reg", "0.01",
        "--lambda_scale_reg", "0.25",
        "--scale_reg_ratio", "5",
        "--reg_from_iter", "1500",
        "--test_iterations", "7000", "15000", "30000",
    ]'''
new_inline_cmd = "    cmd = _build_fastgs_cmd(scene_out, model_path)"

if old_inline_cmd in content:
    content = content.replace(old_inline_cmd, new_inline_cmd, 1)
    print("OK: replaced inline cmd block")
else:
    print("WARNING: inline cmd block not found verbatim")

with open(path, "w") as f:
    f.write(content)

print("Done. Backup saved as app/workers/tasks.py.bak")
