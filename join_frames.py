import subprocess

subprocess.run([
    "ffmpeg", "-y",
    "-framerate", "24",
    "-i", "/workspaces/cse490-p05-starter/part1/frames/f_%04d.png",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-r", "24",
    "/workspaces/cse490-p05-starter/part1/scene.mp4",
], check=True)

print("wrote part1/scene.mp4")
