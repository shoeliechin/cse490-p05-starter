# PLAN.md - Upright spinning torus

## Workspace root
/workspaces/cse490-p05-starter

## Objects
1. Torus - mesh primitive, default ring. Rotated 90 deg on X so the ring stands
   upright (like a wheel): its axis is horizontal and its hole faces sideways.
   Sits at origin.
2. Camera - existing scene camera, framing the torus.
3. Sun - existing scene sun lamp, lighting the torus.

## Motion (2-5 seconds)
Spin the torus about its own Z axis: one full 360 deg turn over 2 seconds.
Keyframes at frame 1 (0 deg) and frame 49 (360 deg), linear interpolation,
so it spins at a constant rate.

## Build order
1. Set up torus: place it and rotate it upright.
2. Keyframe the Z spin (frames 1 to 49).
3. Save part1/scene.blend.

## Notes
- Every path handed to Blender is absolute, from the workspace root.
- Spin is keyframed on the torus object itself (it is the moving part).
