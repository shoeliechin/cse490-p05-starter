import subprocess

cmd = [
    "ffmpeg", "-y",
    "-framerate", "24",
    "-i", "/workspaces/cse490-p05-starter/part1/frames/f_%04d.png",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "/workspaces/cse490-p05-starter/part1/scene.mp4",
]
print(" ".join(cmd))
r = subprocess.run(cmd, capture_output=True, text=True)
print("exit:", r.returncode)
print(r.stdout[-1500:])
print(r.stderr[-1500:])
