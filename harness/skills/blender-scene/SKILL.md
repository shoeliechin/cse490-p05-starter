---
name: blender-scene
description: Plan, build, animate and render a 3D scene in Blender through the Blender tools. Use when a message asks to plan, add, build, animate, render or import something in the scene.
---

# blender-scene

The steps, in order. Each one leaves something a reader can check.

1. Take the scene from the user's message. Read fixtures/scene_brief.md if it exists, and ask the user what you still need to know before you build.
2. Write PLAN.md first: the objects, each built from primitives (cubes, cylinders, spheres, cones, planes), the one camera and one sun lamp, the motion in two to five seconds, and the order you build them in.
3. Show the plan in one short message, then build it. If the user changes the plan, update PLAN.md before you go on.
4. Build one object or one motion per execute_blender_code script. Keep each script short; a long one is cut off on its way back. Every path you hand Blender is absolute, from the workspace root: Blender resolves a relative path against its own folder and says nothing.
5. After each script, save the scene to <part>/scene.blend, where <part> is the folder this build belongs to: part1 for the harness's animation, part2 for OpenCode's, part3 for an optional third. The Blender window shows the result; say what changed in one line.
6. When the user asks to see the scene, render a still: engine BLENDER_WORKBENCH, 640 x 360, PNG to <part>/still.png. Then call get_viewport_screenshot and look at what came back before you answer.
7. Animate with keyframes on separate objects. A physics bake runs in chunks of 24 frames with a save after each; one long call outlasts the server's timeout and loses the socket. Never join moving parts into one mesh; the grader reads motion per object.
8. When the user asks for the render: engine BLENDER_WORKBENCH with the shading colour type set to material and every material's viewport display colour (diffuse_color) set to its base colour, or the frames come out grey; 640 x 360, one PNG per frame into the folder the prompt names (<part>/frames/, file path <part>/frames/f_####), the full frame range. Then join the frames with the installed ffmpeg into <part>/scene.mp4, 24 frames a second, H.264, yuv420p, through a short Python file run with execute. Nothing is written anywhere else.
9. Write transcript.md: the scene the user asked for, your questions and the answers, PLAN.md, every Blender call in order, and where the still and the render landed.
