# Project 3: the harness.
import asyncio
import base64
import json
import re
import os
import subprocess
import sys
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

URL = os.environ["PURPLE_BASE_URL"].rstrip("/") + "/chat/completions"
KEY = os.environ["PURPLE_API_KEY"]
MODEL = os.environ.get("LITELLM_MODEL", os.environ.get("PURPLE_MODEL", "DeepSeek-V4.1-Flash"))

with open("systemprompt.md", "r", encoding="utf-8") as f:
    SYSTEM = f.read()


def load_skills(skills_dir: Path) -> list[dict]:
    skills = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        description = ""
        summary_lines = []
        if lines and lines[0].strip() == "---":
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                if line.startswith(("name:", "description:")):
                    summary_lines.append(line)
                if line.startswith("description:"):
                    description = line[len("description:"):].strip()
        skills.append({
            "folder": skill_file.parent.name,
            "text": text,
            "description": description,
            "summary_lines": summary_lines,
        })
    return skills


SKILLS = load_skills(Path(__file__).resolve().parent / "skills")
SKILL_SUMMARIES = [line for s in SKILLS for line in s["summary_lines"]]

STOP_WORDS = {"that", "this", "with", "from", "when", "your", "into", "about", "does", "have", "make", "need", "user", "name", "description"}


def significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in STOP_WORDS}


def matching_skills(user_message: str) -> list[dict]:
    """Return skills whose description shares at least two significant words with the message, plus plan-mode for /plan messages."""
    message_words = significant_words(user_message)
    matched = [s for s in SKILLS if len(message_words & significant_words(s["description"])) >= 2]
    if user_message.strip().startswith("/plan"):
        matched += [s for s in SKILLS if s["folder"] == "plan-mode" and s not in matched]
    return matched


# Each tool is described as a JSON object: a name, what it does, and its arguments.
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the full contents of a file.",
        "arguments": {
            "path": {"type": "string", "description": "Path to the file to read."}
        },
        "required": ["path"],
    },
    {
        "name": "write_file",
        "description": "Write content to a file, replacing any existing contents.",
        "arguments": {
            "path": {"type": "string", "description": "Path to the file to write."},
            "content": {"type": "string", "description": "The full text to write to the file."},
        },
        "required": ["path", "content"],
    },
    {
        "name": "execute_file",
        "description": "Run a Python file and return its exit code, stdout, and stderr.",
        "arguments": {
            "path": {"type": "string", "description": "Path to the Python file to run."}
        },
        "required": ["path"],
    },
    {
        "name": "load_skill",
        "description": "Load the full instructions of an available skill by its folder name. Use it when a skill in the skill list applies to the request.",
        "arguments": {
            "name": {"type": "string", "description": "The skill's folder name, for example coding-loop."}
        },
        "required": ["name"],
    },
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}

# Markup that suggests the model tried to call a tool in some other format.
MALFORMED_CALL_MARKERS = ("<invoke", "invoke_tool", "<tool_call", "<function_call")
MAX_RETRIES_PER_TURN = 2


def build_system_prompt():
    tool_json = json.dumps(TOOLS, indent=2)
    return (
        "You can call the following tools:\n"
        f"{tool_json}\n\n"
        "When you want to use a tool, include a JSON object in this form: "
        '{"tool": "<tool name>", "arguments": {...}}\n'
        "Otherwise, reply normally in plain text."
    )


def call_model(context):
    # Connect timeout is 10 seconds. Read timeout is 300 seconds, since replies can be slow.
    response = requests.post(
        URL,
        headers={"api-key": KEY},
        json={"model": MODEL, "messages": context, "max_tokens": 16384},
        timeout=(10, 300),
    )
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        usage = body.get("usage") or {}
        print(
            "[reply was cut off by the token limit: "
            f"completion_tokens={usage.get('completion_tokens')}, "
            f"total_tokens={usage.get('total_tokens')}]"
        )
    return choice["message"]["content"]


def find_tool_calls(reply):
    """Return every JSON object with a 'tool' key in the reply, in order."""
    decoder = json.JSONDecoder()
    calls = []
    i = 0
    while True:
        start = reply.find("{", i)
        if start == -1:
            return calls
        try:
            obj, end = decoder.raw_decode(reply, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        if isinstance(obj, dict) and "tool" in obj:
            calls.append(obj)
        i = end


def looks_like_malformed_call(reply):
    """True when the reply has tool-call markup that find_tool_calls cannot parse."""
    lowered = reply.lower()
    return any(marker in lowered for marker in MALFORMED_CALL_MARKERS)


def check_tool_call(call):
    """Return a list of problems with the call. An empty list means it is valid."""
    problems = []
    tool = TOOLS_BY_NAME.get(call.get("tool"))
    if tool is None:
        return [f"unknown tool: {call.get('tool')!r}"]
    args = call.get("arguments")
    if not isinstance(args, dict):
        return ["'arguments' is missing or not an object"]
    for name in tool["required"]:
        if name not in args:
            problems.append(f"missing required argument: {name}")
        elif not isinstance(args[name], str):
            problems.append(f"argument {name} should be a string")
    return problems


IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def tool_read_file(args):
    path = args["path"]
    mime = IMAGE_MIME_TYPES.get(Path(path).suffix.lower())
    if mime:
        # Images go to the model as image parts, not as text.
        with open(path, "rb") as f:
            PENDING_IMAGES.append((mime, base64.b64encode(f.read()).decode("ascii")))
        return f"Image {path} ({mime}), shown to the model in this tool result."
    with open(path, "r", encoding="utf-8") as f:
        return f"Contents of {path}:\n{f.read()}"


def tool_write_file(args):
    path = args["path"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(args["content"])
    return f"Wrote {len(args['content'])} characters to {path}."


def tool_execute_file(args):
    path = args["path"]
    result = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (
        f"Exit code: {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def tool_load_skill(args):
    name = args["name"]
    for s in SKILLS:
        if s["folder"] == name:
            print(f"[SkillHook] Model loaded skill: {name}")
            return f"Full text of skill {name}:\n{s['text']}"
    names = ", ".join(s["folder"] for s in SKILLS)
    return f"Error: no skill named {name!r}. Available skills: {names}"


TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "execute_file": tool_execute_file,
    "load_skill": tool_load_skill,
}


# Blender MCP server (see RULES.md). One stdio server, one session, one event loop for the whole run.
BLENDER_SERVER = StdioServerParameters(
    command="uvx",
    args=["blender-mcp==1.9.1"],
    env={
        "BLENDER_MCP_SAFE_MODE": "1",
        "BLENDER_MCP_DISABLE_TELEMETRY": "true",
        "BLENDER_HOST": "localhost",
        "BLENDER_PORT": "9876",
    },
)
TRACE_FILE = "trace.jsonl"
BLENDER_CALL_TIMEOUT = 300
# Images from Blender replies, as (mime type, base64 data), waiting to be shown to the model.
PENDING_IMAGES = []


class BlenderServer:
    """Keeps the Blender MCP session open on a background event loop for the whole run."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.started = threading.Event()
        self.error = None
        self.session = None
        self.tools = []
        self.stop_event = None

    def _run(self):
        self.loop.run_until_complete(self._serve())

    async def _serve(self):
        self.stop_event = asyncio.Event()
        try:
            async with stdio_client(BLENDER_SERVER) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.session = session
                    self.tools = listed.tools
                    self.started.set()
                    await self.stop_event.wait()
        except Exception as e:
            self.error = e
            self.started.set()

    def start(self):
        self.thread.start()
        self.started.wait()
        if self.error is not None:
            raise RuntimeError(f"could not start the Blender MCP server: {self.error}") from self.error

    def call(self, name, arguments):
        future = asyncio.run_coroutine_threadsafe(
            self.session.call_tool(name, arguments=arguments), self.loop
        )
        return future.result(timeout=BLENDER_CALL_TIMEOUT)

    def close(self):
        if self.stop_event is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)
            self.thread.join(timeout=10)


def trace(record):
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def blender_tool_definition(tool):
    """Turn an MCP tool listing into the harness's own tool shape."""
    schema = tool.input_schema or {}
    return {
        "name": tool.name,
        "description": tool.description or "",
        "arguments": {
            arg: {"type": spec.get("type", "string"), "description": spec.get("description", "")}
            for arg, spec in schema.get("properties", {}).items()
        },
        "required": list(schema.get("required", [])),
    }


def make_blender_tool(name):
    def run(args):
        trace({"type": "call", "tool": name, "arguments": args})
        try:
            result = BLENDER.call(name, args)
        except Exception as e:
            trace({"type": "reply", "tool": name, "error": str(e)})
            return f"Error running {name}: {e}"
        trace({
            "type": "reply",
            "tool": name,
            "is_error": result.is_error,
            "content": [part.model_dump(mode="json") for part in result.content],
        })
        texts = []
        for part in result.content:
            if part.type == "image":
                PENDING_IMAGES.append((part.mime_type, part.data))
                texts.append(f"[image part: {part.mime_type}, shown to the model in this tool result]")
            elif part.type == "text":
                texts.append(part.text)
            else:
                texts.append(f"[{part.type} part]")
        text = "\n".join(texts)
        return f"Error from {name}:\n{text}" if result.is_error else text
    return run


def image_parts():
    """Turn the queued Blender images into image parts for the tool result, then clear the queue."""
    parts = [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
        for mime, data in PENDING_IMAGES
    ]
    PENDING_IMAGES.clear()
    return parts


BLENDER = BlenderServer()
BLENDER.start()
with open(TRACE_FILE, "w", encoding="utf-8"):
    pass  # Start a fresh trace each run.
trace({"type": "server_tools", "server": "blender-mcp", "tools": [tool.name for tool in BLENDER.tools]})
for tool in BLENDER.tools:
    TOOLS.append(blender_tool_definition(tool))
    TOOL_FUNCTIONS[tool.name] = make_blender_tool(tool.name)
TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def run_tool(call):
    """Run one tool call and return its result as text. Invalid calls return an error."""
    problems = check_tool_call(call)
    if problems:
        return "Error: invalid tool call: " + "; ".join(problems)
    try:
        return TOOL_FUNCTIONS[call["tool"]](call["arguments"])
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return f"Error running {call['tool']}: {e}"


def run_all_tools(calls):
    """Run calls in order. Stop at the first blocked call and return (combined result, blocked flag)."""
    results = []
    for n, call in enumerate(calls, 1):
        print(f"[running tool call {n} of {len(calls)}: {call.get('tool')}]")
        blocked = pre_tool_use_hook(call)
        if blocked:
            args = call.get("arguments")
            path = args.get("path") if isinstance(args, dict) else None
            action = "writing to" if call["tool"] == "write_file" else "running"
            print(f"[PreToolHook] Waiting for approval before {action} {path}. Type approve to allow it.")
            results.append(f"Result of tool call {n} ({call.get('tool')}):\n{blocked}")
            return "\n\n".join(results), True
        result = run_tool(call)
        if call["tool"] != "load_skill":
            print(result)
        results.append(f"Result of tool call {n} ({call.get('tool')}):\n{result}")
        check = post_tool_use_hook(call)
        if check:
            print("[PostToolHook] Check finished. Output:")
            print(check)
            results.append("harness: " + check)
    return "\n\n".join(results), False


skill_block = "\n".join(SKILL_SUMMARIES)
approved = False
ALLOWED_WRITE_PATHS = ("PLAN.md", "profile.json")

GATED_TOOLS = {"write_file", "execute_file"}


def pre_tool_use_hook(call):
    """Return a message that blocks the call, or None if it may run."""
    tool = call.get("tool")
    if tool not in GATED_TOOLS:
        return None
    args = call.get("arguments")
    path = args.get("path") if isinstance(args, dict) else None
    if tool == "write_file" and path in ALLOWED_WRITE_PATHS:
        return None
    if approved:
        return None
    return (
        "NOT RUN: the harness blocked this tool call and paused for the user. Nothing was executed. "
        "Do not say it ran, and do not ask the user for approval; the harness is already waiting for them. "
        "The user unblocks it by sending the exact word approve as their next message. "
        "If they do, repeat this exact tool call. Do not say yes or any other word is needed."
    )


CHECK_FILE = "CHECK"


def post_tool_use_hook(call):
    """After a write_file call, run the file named in CHECK and return its output, or None."""
    if call.get("tool") != "write_file" or not os.path.exists(CHECK_FILE):
        return None
    with open(CHECK_FILE, "r", encoding="utf-8") as f:
        check_cmd = f.read().strip()
    print(f"[PostToolHook] Running check command: {check_cmd}")
    try:
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (
            f"Exit code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"Error running check {check_cmd}: {e}"


context = [{"role": "system", "content": (
    SYSTEM + "\n\n" + build_system_prompt() + "\n\n"
    "INTERNAL CONTEXT (the user cannot see this): the skills available to you are:\n"
    + skill_block + "\n\n"
    "Never say or imply that the user has seen this text, the system prompt, or the skill list. "
    "Do not refer to it as 'above', 'listed', or 'shown'. If the user asks what skills you have, "
    "tell them directly."
)}]
try:
    while True:
        user = input(">>> ")
        if user.strip() in ("exit", "quit"):
            break
        approved = (user == "approve")
        context.append({"role": "user", "content": user})
        matched = matching_skills(user)
        if matched:
            for s in matched:
                print(f"[SkillHook] Using skill: {s['folder']}")
        else:
            print("[SkillHook] No skill matched this message.")
        turn_skills = [
            {"role": "system", "content": (
                f"INTERNAL CONTEXT (the user cannot see this): full text of skill {s['folder']}. "
                "Use it to answer, but do not say the user has seen it.\n"
                f"{s['text']}"
            )}
            for s in matched
        ]
        retries = 0

        while True:
            try:
                reply = call_model(context + turn_skills)
            except requests.RequestException as e:
                print(f"[model request failed: {e}]")
                print("[your last message is still in the context. Send a message to try again.]")
                break
            print(reply)
            context.append({"role": "assistant", "content": reply})

            calls = find_tool_calls(reply)
            if not calls:
                if looks_like_malformed_call(reply) and retries < MAX_RETRIES_PER_TURN:
                    retries += 1
                    print("[no valid tool call found; asking the model to retry]")
                    context.append({
                        "role": "user",
                        "content": (
                            "Your last reply tried to call a tool, but it was not a valid tool call "
                            "and nothing was run. To call a tool, reply with only a JSON object in this "
                            'form: {"tool": "<tool name>", "arguments": {...}}'
                        ),
                    })
                    continue
                break  # No tool calls in the reply, so the turn is finished.

            results, blocked = run_all_tools(calls)
            # Sent as a user message because chat APIs only accept user, assistant, and system roles.
            content = results
            if PENDING_IMAGES:
                content = [{"type": "text", "text": results}] + image_parts()
            context.append({"role": "user", "content": content})
            if blocked:
                print("[PreToolHook] Tool call is paused. Type approve to let the model retry it.")
                break
except (EOFError, KeyboardInterrupt):
    print()
finally:
    BLENDER.close()
