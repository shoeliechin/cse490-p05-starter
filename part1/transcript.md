# transcript.md - Upright spinning torus (part1)

## The scene the user asked for
An upright spinning torus: a torus stood on edge so its ring is like a wheel, spinning
about its own Z (hub) axis. The blend file in part1/ had been overwritten, so the task
was to rebuild it and recover the scene.

## Questions and answers
- Q: The scene brief (fixtures/scene_brief.md) is an empty template and the scene was
  reset, so I asked what to keep. A: The user pointed me at the existing part1/PLAN.md,
  which specifies an upright torus spinning 360 deg about Z over frames 1-49.
- Q: The default Cube sits at the origin and would hide the torus. Delete it? A: Yes,
  approved.
- Q: Later, render the animation to PNG frames and join to mp4? A: Yes.
- Q: Do the remaining skill items (still + transcript)? A: Yes.
- Q: The first renders sliced the bottom off the torus (out of frame). A: Yes, redo.
  Camera was moved back and re-aimed; still, frames and mp4 all re-rendered.
- Q: The rendered video had artifacts / old stills in it. A: The user cleared
  part1/frames/ and kept the good frames; only the mp4 was re-joined.

## PLAN.md (already in part1/PLAN.md)
Upright torus; Camera; Sun. Spin about the torus's own Z, one full 360 deg turn over
2 s, keyframes at frame 1 (0 deg) and frame 49 (360 deg), linear interpolation.

## Blender calls, in order
1. get_scene_info / get_object_info - found the starter default (Cube, Light, Camera),
   no torus.
2. execute_blender_code - removed the default Cube; added a torus at the origin
   (major 1.0, minor 0.25); rotated 90 deg on X to stand it upright.
3. execute_blender_code - keyframed the Z spin, frames 1 to 49, linear (first attempt
   hit a slotted-action error; retried via layers/strips/channelbags).
4. execute_blender_code - framed the camera on the torus and saved
   /workspaces/cse490-p05-starter/part1/scene.blend.
5. execute_blender_code - verified the saved scene: Torus at origin, rot X 1.5708,
   frame range 1-49, rot 0 @f1, 3.1416 @f25, 6.2832 @f49.
6. execute_blender_code - set engine BLENDER_WORKBENCH, 640x360, MATERIAL colour,
   material viewport colour on the torus, output part1/frames/f_ .
7. execute_blender_code - rendered the animation, frames 1 to 49.
8. execute_file join_frames.py - joined part1/frames/f_%04d.png into
   part1/scene.mp4, H.264, yuv420p, 24 fps.
9. execute_blender_code - rendered the still part1/still.png at frame 1.

### Camera fix (cutoff issue)
10. execute_blender_code - measured the torus world bbox: x/z are +/-1.25 (2.5 m tall),
    y is only +/-0.25. The camera at (0,-6,1.5) aimed at z=0.5 with a 50 mm lens left
    only ~+/-1.09 m covered, so the bottom of the torus fell out of frame.
11. execute_blender_code - moved the camera to (0,-9,0), aimed straight at the origin
    (rot X 1.5708). At 9 m the frame covers ~+/-1.823 m, so the whole 2.5 m torus fits
    with headroom. Saved part1/scene.blend again and re-rendered part1/still.png.
12. execute_blender_code - re-rendered frames 1 to 49 with the corrected camera.
13. get_viewport_screenshot - checked the scene; torus fully in frame.
14. execute_blender_code - loaded part1/still.png and sampled pixel rows: bottom rows
    carry real content (energy ~55), matching top/middle, so no cutoff.
15. execute_file join_frames.py - re-joined the corrected frames into part1/scene.mp4.

### Artifact fix (stale frames in the video)
16. The first join read 121 frames / 5.04 s: stale PNGs in part1/frames/ had been
    picked up by ffmpeg's f_%04d.png pattern (ffmpeg's 24 -> 12288 tbn rounding also
    duplicated frames). The user cleared part1/frames/ and kept the good 49 frames.
17. execute_file join_frames.py - re-joined the clean frames into part1/scene.mp4.
    ffmpeg now reports 49 frames, duration 00:00:02.04, H.264, yuv420p, 24 fps - one
    clean 2-second loop, no stale or duplicated frames.

## Where things landed
- Scene:  part1/scene.blend  (camera at (0,-9,0) aiming at origin)
- Still:  part1/still.png  (BLENDER_WORKBENCH, 640x360, frame 1, full torus)
- Frames: part1/frames/f_0001.png ... f_0049.png  (640x360, 24 fps, full torus)
- Render: part1/scene.mp4  (H.264, yuv420p, 24 fps, full torus, 49 frames / 2.04 s)
- Helper: join_frames.py (workspace root)
