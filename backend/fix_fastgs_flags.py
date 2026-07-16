path = "app/workers/tasks.py"
with open(path) as f:
    content = f.read()

with open(path + ".bak2", "w") as f:
    f.write(content)

old = '''        "--lambda_dssim", "0.3",
        "--lambda_opacity_reg", "0.01",
        "--lambda_scale_reg", "0.25",
        "--scale_reg_ratio", "5",
        "--reg_from_iter", "1500",
        "--test_iterations", "7000", "15000", "30000",'''

new = '''        "--lambda_dssim", "0.3",
        "--test_iterations", "7000", "15000", "30000",'''

if old in content:
    content = content.replace(old, new, 1)
    print("OK: removed unsupported flags")
else:
    print("WARNING: exact block not found — no changes made")

with open(path, "w") as f:
    f.write(content)
