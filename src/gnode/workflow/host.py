"""The node protocol host: runs one step instance's body and turns what it returns into a result.

A body receives a ``Ctx``. It reads what it declared, calls paid capabilities through
gnode, reports facts and annotations, and returns its declared outputs. Everything else
belongs to the engine: staging inputs, validating and storing outputs, the call cache,
the budget, the record. This host runs bodies in process; the request and response it
builds are the node protocol's, so an out-of-process host can replace it.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import shutil
import subprocess
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from gnode.workflow import expr
from gnode.workflow.expand import Instance, Result
from gnode.workflow.routes import Route
from gnode.workflow.spec import NodeSpec
from gnode.workflow.store import CallRecord, JobRecord, Store, files_in
from gnode.workflow.values import MISSING, Collection, FileValue, plain

#: Turn a staged file into a convenient object (``ctx.read.image`` returns a picture).
Reader = Callable[[Path], Any]
#: Turn an object into bytes for an output (``ctx.out.png`` encodes a picture).
Writer = Callable[[Any], bytes]

READERS: dict[str, Reader] = {}
WRITERS: dict[str, tuple[Writer, str]] = {}

ANNOTATIONS_KIND = "gnode-annotations-v1"
SHAPES = ("point", "points", "box")


def register_reader(kind: str, reader: Reader) -> None:
    READERS[kind] = reader


def register_writer(name: str, writer: Writer, kind: str) -> None:
    WRITERS[name] = (writer, kind)


class NodeFailure(Exception):
    """A broken result: the step fails with this message. It is not a take."""


class CapabilityError(RuntimeError):
    """A paid call that cannot be made: no route, not live, no handler, over the ceiling."""


class CallRefused(CapabilityError):
    """A provider adapter refused a call before sending anything, so nothing was billed.

    Any other error from a handler leaves the call's whole worst case charged: once a
    request may have left, nobody can say it did not bill.
    """


# ---------------------------------------------------------------------------- inputs


@dataclass(frozen=True, slots=True)
class InputFile:
    """A staged input: read it; never write to it."""

    path: Path
    kind: str
    digest: str
    key: str | None
    value: FileValue

    @property
    def facts(self) -> Mapping[str, Any]:
        return self.value.expression_facts()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def copy_to(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, target)
        return target


@dataclass(frozen=True, slots=True)
class Output:
    """One value a body returns for an output: bytes, or a file it wrote."""

    data: bytes
    kind: str


@dataclass
class CallResult:
    """What a capability returned: its files, its data, what it cost."""

    files: dict[str, InputFile]
    data: Any
    cost_usd: float | None
    cached: bool

    @property
    def image(self) -> InputFile:
        return self._first("image")

    @property
    def audio(self) -> InputFile:
        return self._first("audio")

    @property
    def video(self) -> InputFile:
        return self._first("video")

    @property
    def json(self) -> Any:
        return self.data

    def _first(self, family: str) -> InputFile:
        for file in self.files.values():
            if file.kind.split("/", 1)[0] == family:
                return file
        raise CapabilityError(f"the call returned no {family}")

    def pil(self) -> Any:
        return READERS["image"](self.image.path)


#: A capability: given the route, the request (files by staged path) and the take,
#: return the files and data the provider produced, and the cost when it says so.
CapabilityHandler = Callable[[Route, Mapping[str, Any], int], Awaitable[CallRecord]]


class JobLog:
    """Where a long job writes down each submission: before it leaves, and once taken.

    ``submitting()`` before a request may leave; ``submitted(handle)`` once the provider
    acknowledged it, with what collecting it needs (no credentials: the record is kept in
    the cache); ``settled()`` once nothing of the call is outstanding, such as a job the
    provider reported failed before the handler submits a retry.
    """

    def __init__(self, store: Store, key: str, capability: str, route: str, take: int) -> None:
        self._store = store
        self._job = JobRecord(key, capability, route, take, "submitting")

    def submitting(self) -> None:
        self._store.save_job(self._job)

    def submitted(self, handle: Mapping[str, Any]) -> None:
        json.dumps(handle)
        self._store.save_job(replace(self._job, state="submitted", handle=dict(handle)))

    def settled(self) -> None:
        self._store.clear_job(self._job.key)


@dataclass(frozen=True, slots=True)
class LongJob:
    """A capability whose provider job outlives one request: submitted once, then collected.

    ``start(route, request, take, log)`` submits and collects, telling ``log`` before each
    request may leave and the handle the provider took it under. ``collect(route, request,
    take, handle, log)`` collects a job an interrupted run submitted, and never submits;
    it settles ``log`` when the job ended without a result, so the next run submits anew.
    """

    start: Callable[[Route, Mapping[str, Any], int, JobLog], Awaitable[CallRecord]]
    collect: Callable[
        [Route, Mapping[str, Any], int, Mapping[str, Any], JobLog], Awaitable[CallRecord]
    ]


@dataclass
class Spending:
    """The run's ledger as the host sees it: hold before a call, settle the hold after.

    ``reserve(instance_id, worst_case_usd)`` returns the hold; ``settle(hold, cost)``
    charges the reported cost, or the whole hold when the provider reported none.
    """

    reserve: Callable[[str, float], Awaitable[str]]
    settle: Callable[[str, float | None], None]


@dataclass
class HostServices:
    """What bodies may reach: capabilities, tools, the store, the ledger, the clock."""

    store: Store
    capabilities: Mapping[str, CapabilityHandler | LongJob] = field(default_factory=dict)
    live: bool = False
    spending: Spending | None = None
    work_root: Path | None = None
    on_call: Callable[[Mapping[str, Any]], None] | None = None
    on_progress: Callable[[str, str, float | None], None] | None = None


# ----------------------------------------------------------------------------- ctx


class _Read:
    def __init__(self, ctx: Ctx) -> None:
        self._ctx = ctx

    def _one(self, name: str) -> InputFile:
        value = self._ctx.inputs.get(name)
        if not isinstance(value, InputFile):
            raise NodeFailure(f"input {name} is not one file")
        return value

    def bytes(self, name: str) -> bytes:
        return self._one(name).read_bytes()

    def text(self, name: str) -> str:
        return self.bytes(name).decode("utf-8")

    def json(self, name: str) -> Any:
        return json.loads(self.bytes(name))

    def annotations(self, name: str) -> Any:
        return self.json(name)

    def image(self, name: str) -> Any:
        reader = READERS.get("image")
        if reader is None:
            raise NodeFailure("reading images needs gnode-std installed")
        return reader(self._one(name).path)


class _Out:
    def __init__(self, ctx: Ctx) -> None:
        self._ctx = ctx

    def bytes(self, data: bytes, kind: str) -> Output:
        return Output(bytes(data), kind)

    def text(self, text: str, kind: str = "text/plain") -> Output:
        return Output(text.encode("utf-8"), kind)

    def json(self, value: Any) -> Output:
        return Output(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8"), "json"
        )

    def png(self, picture: Any) -> Output:
        writer = WRITERS.get("png")
        if writer is None:
            raise NodeFailure("writing images needs gnode-std installed")
        encode, kind = writer
        return Output(encode(picture), kind)

    def path(self, name: str) -> Path:
        return self._ctx.work_path(f"out/{name}")

    def file(self, path: Path, kind: str | None = None) -> Output:
        from gnode.workflow.registry import kind_of

        return Output(Path(path).read_bytes(), kind or kind_of(Path(path)))


class _Tool:
    def __init__(self, ctx: Ctx, name: str, executable: str) -> None:
        self._ctx = ctx
        self.name = name
        self.executable = executable

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_s: float | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run the declared program in a session of its own.

        A timeout ends the program and everything it started. With ``check`` (the default) a
        non-zero exit fails the step with its output; without, the caller reads the exit.
        ``env`` replaces the inherited environment when given.
        """

        process = subprocess.Popen(
            [self.executable, *argv],
            cwd=cwd or self._ctx.work_path("."),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=None if env is None else dict(env),
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _end_session(process)
            raise NodeFailure(f"{self.name} ran past {timeout_s} seconds") from None
        completed = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        if check and completed.returncode != 0:
            tail = (completed.stderr or completed.stdout).strip()[-2_000:]
            raise NodeFailure(f"{self.name} exited {completed.returncode}: {tail}")
        return completed


def _end_session(process: subprocess.Popen[str]) -> None:
    import contextlib
    import os
    import signal

    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.communicate()


def tool_name(entry: str) -> str:
    """The program a ``tools=`` entry names, without its version bound (``blender>=4.2``)."""

    return entry.split(">", 1)[0].split("=", 1)[0].strip()


def resolve_tool(name: str) -> str | None:
    """Where a declared program is: ``GNODE_TOOL_<NAME>`` when set, else on ``PATH``."""

    import os

    configured = os.environ.get(f"GNODE_TOOL_{name.upper().replace('-', '_')}")
    if configured:
        return configured if Path(configured).is_file() else None
    return shutil.which(name)


class Ctx:
    """What a node body gets: its inputs, settings, capabilities, and where to report."""

    def __init__(
        self,
        instance: Instance,
        *,
        inputs: Mapping[str, Any],
        params: Mapping[str, Any],
        services: HostServices,
        project_root: Path,
        work_dir: Path,
    ) -> None:
        self.instance = instance
        self.spec = instance.spec
        self.inputs = dict(inputs)
        self.params = dict(params)
        self.state: dict[str, Any] = {}
        self.read = _Read(self)
        self.out = _Out(self)
        self.facts: dict[str, Any] = {}
        self.marks: list[dict[str, Any]] = []
        self.cost_usd = 0.0
        self.calls = 0
        self._services = services
        self._project_root = project_root
        self._work_dir = work_dir
        self._calls_made: dict[str, int] = {}
        self._cancel = asyncio.Event()

    # ------------------------------------------------------------- reporting

    def fact(self, name: str, value: Any) -> None:
        """Report a small value: a score, a verdict, a measurement."""

        json.dumps(value)
        self.facts[name] = value

    def annotate(
        self,
        *,
        shape: str | None = None,
        label: str | None = None,
        color: str | None = None,
        tag: str | None = None,
        **fields: Any,
    ) -> None:
        """Add one mark to this node's ``annotations`` output.

        ``shape`` is ``point`` (``at=[x, y]``), ``points`` (``points=[[x, y], ...]``,
        ``closed``) or ``box`` (``box=[x0, y0, x1, y1]``), in coordinates from 0 to 1;
        no shape is a note about the whole image.
        """

        mark: dict[str, Any] = {}
        if shape is not None:
            if shape not in SHAPES:
                raise NodeFailure(f"a mark's shape is one of {', '.join(SHAPES)}")
            mark["shape"] = shape
            geometry = {"point": "at", "points": "points", "box": "box"}[shape]
            if geometry not in fields:
                raise NodeFailure(f"a {shape} mark needs {geometry}=")
        for name, value in (("label", label), ("color", color), ("tag", tag)):
            if value is not None:
                mark[name] = value
        mark.update(fields)
        json.dumps(mark)
        self.marks.append(mark)

    def progress(self, text: str, fraction: float | None = None) -> None:
        if self._services.on_progress is not None:
            self._services.on_progress(self.instance.id, text, fraction)

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def fail(self, message: str) -> NodeFailure:
        return NodeFailure(message)

    # ---------------------------------------------------------------- places

    def work_path(self, name: str) -> Path:
        path = (self._work_dir / name).resolve()
        if not path.is_relative_to(self._work_dir.resolve()):
            raise NodeFailure(f"{name} is outside this node's work folder")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def prompt(self, path: str, **variables: Any) -> str:
        """Render a declared resource, or a file passed in ``with:``, with ``${{ }}``."""

        if path not in self.spec.resources:
            raise NodeFailure(f"{path} is not one of this node's declared resources")
        source = expr.prompt_text((self._project_root / path).read_text(encoding="utf-8"))
        return render_template(source, {**self.params, **variables})

    def tool(self, name: str) -> _Tool:
        declared = {tool_name(entry) for entry in self.spec.tools}
        if name not in declared:
            raise NodeFailure(f"{name} is not one of this node's declared tools")
        executable = resolve_tool(name)
        if executable is None:
            raise NodeFailure(f"{name} is not installed (see gnode doctor)")
        return _Tool(self, name, executable)

    # ---------------------------------------------------------- capabilities

    async def capability(self, name: str, **request: Any) -> CallResult:
        """A paid call through gnode: routed, priced, budgeted, recorded and call-cached."""

        allowed = self.spec.capability_calls(self.params)
        if name not in allowed:
            raise CapabilityError(
                f"{self.spec.name} calls {name} without declaring it (calls={{'{name}': N}})"
            )
        made = self._calls_made.get(name, 0)
        if made >= allowed[name]:
            raise CapabilityError(f"{self.spec.name} declared at most {allowed[name]} {name} calls")
        self._calls_made[name] = made + 1
        route = self.instance.routes.get(name)
        if route is None:
            raise CapabilityError(f"no route serves {name} for {self.instance.step}")
        result = await call_capability(
            self._services,
            name,
            route,
            _stored(self._services.store, _staged_request(request)),
            take=self.instance.take,
            take_path=self.instance.takes,
            instance_id=self.instance.id,
        )
        if not result.cached:
            self.calls += 1
            self.cost_usd += result.cost_usd or 0.0
        return result

    async def image_generate(self, **request: Any) -> CallResult:
        return await self.capability("image.generate", **request)

    async def image_edit(self, **request: Any) -> CallResult:
        return await self.capability("image.edit", **request)

    async def structured_generate(self, **request: Any) -> CallResult:
        return await self.capability("structured.generate", **request)

    def agent(
        self,
        *,
        system: str,
        tools: Sequence[Callable[..., Any]] = (),
        recent_images: int | None = None,
        max_tokens: int | None = None,
    ) -> Agent:
        """A tool-using model loop; declare its turns with ``calls={"agent.turn": N}``."""

        return Agent(
            self, system=system, tools=tools, recent_images=recent_images, max_tokens=max_tokens
        )


def tool(function: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a function as a tool an agent may call; its docstring is its description.

    Its first parameter is the node's ``ctx``; the rest, with their annotations, are the
    arguments the model fills in.
    """

    function.gnode_tool = True  # type: ignore[attr-defined]
    return function


_JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def tool_schema(function: Callable[..., Any]) -> dict[str, Any]:
    """What the model is told about a tool: its name, description and arguments."""

    signature = inspect.signature(function)
    hints = function.__annotations__
    properties: dict[str, Any] = {}
    required: list[str] = []
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if index == 0:
            continue  # ctx
        annotation = hints.get(name, str)
        if isinstance(annotation, str):
            annotation = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
            }.get(annotation, str)
        properties[name] = {"type": _JSON_TYPES.get(annotation, "string")}
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "name": function.__name__,
        "description": inspect.getdoc(function) or function.__name__,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


@dataclass(frozen=True, slots=True)
class ToolReply:
    """What a tool hands back when the model should see pictures as well as words."""

    text: str
    images: Sequence[Any] = ()


#: The tool an agent calls to finish, when its node asks for a structured answer.
SUBMIT = "submit"


class Agent:
    """A tool-using model loop inside a node; every model turn is a paid, call-cached call.

    Each turn sends the transcript so far to the ``agent.turn`` capability and gets back
    text and tool calls. The tools run here, in the node's process, and their results join
    the transcript; a tool may return a ``ToolReply`` to show the model pictures. A resumed
    run replays the turns it already paid for: an identical transcript is an identical
    request. Pictures travel as files, so a request is keyed by their digests.

    With ``submit=`` (a JSON Schema), the model must finish by calling ``submit``; an answer
    the schema or ``check`` refuses goes back to the model as the tool's result, and the
    loop goes on. ``recent_images`` keeps only the newest pictures in each request.
    """

    def __init__(
        self,
        ctx: Ctx,
        *,
        system: str,
        tools: Sequence[Callable[..., Any]],
        recent_images: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._tools: dict[str, Any] = {}
        for function in tools:
            name = _tool_name(function)
            if name == SUBMIT:
                raise NodeFailure(f"{SUBMIT} is the agent's own tool; name yours otherwise")
            self._tools[name] = function
        self._ctx = ctx
        self._system = system
        self._recent_images = recent_images
        self._max_tokens = max_tokens
        self.transcript: list[dict[str, Any]] = []

    async def run(
        self,
        instructions: str,
        *,
        max_steps: int,
        images: Sequence[Any] = (),
        submit: Mapping[str, Any] | None = None,
        check: Callable[[Any], None] | None = None,
    ) -> Any:
        """Turn by turn until the model answers (or submits), or ``max_steps``.

        Returns the final text, or with ``submit`` the submitted value.
        """

        opening: dict[str, Any] = {"role": "user", "content": instructions}
        if images:
            opening["images"] = [self._picture(image) for image in images]
        self.transcript.append(opening)
        schemas = [_declared_schema(function) for function in self._tools.values()]
        if submit is not None:
            schemas.append(
                {
                    "name": SUBMIT,
                    "description": "Finish: submit the answer this task asks for.",
                    "parameters": dict(submit),
                }
            )
        validator = None if submit is None else _validator(submit)
        for _ in range(max_steps):
            request: dict[str, Any] = {
                "system": self._system,
                "messages": self._window(),
                "tools": schemas,
                "tool_choice": "required" if submit is not None else "auto",
            }
            if self._max_tokens is not None:
                request["max_tokens"] = self._max_tokens
            reply = await self._ctx.capability("agent.turn", **request)
            data = reply.data if isinstance(reply.data, Mapping) else {}
            calls = list(data.get("tool_calls", []))
            self.transcript.append(
                {"role": "assistant", "content": data.get("text", ""), "tool_calls": calls}
            )
            if not calls:
                if submit is None:
                    return str(data.get("text", ""))
                self.transcript.append({"role": "user", "content": f"Finish by calling {SUBMIT}."})
                continue
            for call in calls:
                name = str(call.get("name", ""))
                arguments = dict(call.get("arguments", {}))
                if name == SUBMIT and validator is not None:
                    refusal = _refusal(validator, check, arguments)
                    if refusal is None:
                        return arguments
                    self._answer(call, f"refused: {refusal}")
                    continue
                self._answer(call, await self._call(name, arguments))
        raise NodeFailure(f"the agent did not finish within {max_steps} turns")

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        function = self._tools.get(name)
        if function is None:
            return f"no tool named {name}"
        try:
            if _is_declared(function):
                result = function.handler(arguments)
            else:
                result = function(self._ctx, **arguments)
            if inspect.isawaitable(result):
                result = await result
        except NodeFailure:
            raise
        except Exception as error:
            return f"{type(error).__name__}: {error}"
        if _is_declared(function):
            return ToolReply(str(result.text), tuple(result.images))
        return result

    def _answer(self, call: Mapping[str, Any], result: Any) -> None:
        message: dict[str, Any] = {"role": "tool", "name": call.get("name")}
        if call.get("id") is not None:
            message["tool_call_id"] = call.get("id")
        if isinstance(result, ToolReply):
            message["content"] = result.text
            if result.images:
                message["images"] = [self._picture(image) for image in result.images]
        else:
            message["content"] = _tool_text(result)
        self.transcript.append(message)

    def _picture(self, image: Any) -> FileValue:
        """A picture as a stored file: what the request is keyed by."""

        store = self._ctx._services.store
        if isinstance(image, InputFile):
            return image.value
        if isinstance(image, FileValue):
            return image
        if isinstance(image, Output):
            return store.put_bytes(image.data, kind=image.kind, name="agent/image")
        if isinstance(image, str) and image.startswith("data:"):
            header, _, encoded = image.partition(",")
            kind = header.removeprefix("data:").split(";", 1)[0] or "image/png"
            return store.put_bytes(base64.b64decode(encoded), kind=kind, name="agent/image")
        if isinstance(image, Path | str):
            path = Path(image)
            return store.put_bytes(path.read_bytes(), kind=_image_kind(path), name=path.name)
        raise NodeFailure(f"an agent picture is a file, not {type(image).__name__}")

    def _window(self) -> list[dict[str, Any]]:
        """The transcript as it is sent: only the newest ``recent_images`` pictures."""

        if self._recent_images is None:
            return [dict(message) for message in self.transcript]
        keep = self._recent_images
        sent: list[dict[str, Any]] = []
        for message in reversed(self.transcript):
            images = list(message.get("images", []))
            if not images:
                sent.append(dict(message))
                continue
            shown = images[len(images) - keep :] if keep > 0 else []
            keep -= len(shown)
            dropped = len(images) - len(shown)
            copy = {key: value for key, value in message.items() if key != "images"}
            if shown:
                copy["images"] = shown
            if dropped:
                copy["content"] = (
                    f"{copy.get('content', '')}\n[{dropped} older picture(s) not shown]"
                )
            sent.append(copy)
        return list(reversed(sent))


def _is_declared(tool: Any) -> bool:
    """A tool declared by its schema (a name, description, parameters and handler)."""

    return all(hasattr(tool, field) for field in ("name", "description", "parameters", "handler"))


def _tool_name(tool: Any) -> str:
    if _is_declared(tool):
        return str(tool.name)
    if not getattr(tool, "gnode_tool", False):
        raise NodeFailure(f"{getattr(tool, '__name__', tool)} is not declared with @tool")
    return str(tool.__name__)


def _declared_schema(tool: Any) -> dict[str, Any]:
    if _is_declared(tool):
        return {
            "name": str(tool.name),
            "description": str(tool.description),
            "parameters": dict(tool.parameters),
        }
    return tool_schema(tool)


def _image_kind(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")


def _validator(schema: Mapping[str, Any]) -> Any:
    try:
        import jsonschema
    except ImportError as error:  # pragma: no cover - a declared dependency
        raise NodeFailure("an agent's submit schema needs jsonschema installed") from error
    return jsonschema.Draft202012Validator(dict(schema))


def _refusal(validator: Any, check: Callable[[Any], None] | None, value: Any) -> str | None:
    problems = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if problems:
        where = "/".join(str(part) for part in problems[0].path) or "the answer"
        return f"{where}: {problems[0].message}"[:500]
    if check is not None:
        try:
            check(value)
        except (ValueError, NodeFailure) as error:
            return str(error)[:500]
    return None


def _tool_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(plain(value), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def render_template(source: str, variables: Mapping[str, Any]) -> str:
    """Render ``${{ name }}`` expressions against ``variables``."""

    class _Vars(expr.Scope):
        def root(self, name: str) -> Any:
            if name not in variables:
                raise expr.ExpressionError(f"the prompt names {name!r}, which nobody gave it")
            return variables[name]

    parsed = expr.template(source)
    if parsed is None:
        return source
    rendered = expr.render(parsed, _Vars())
    return rendered if isinstance(rendered, str) else expr._text(rendered)


def _staged_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """A request with each staged input as the file it is, however deep it sits."""

    def stage(value: Any) -> Any:
        if isinstance(value, InputFile):
            return value.value
        if isinstance(value, list):
            return [stage(item) for item in value]
        if isinstance(value, dict):
            return {key: stage(item) for key, item in value.items()}
        return value

    return {key: stage(value) for key, value in request.items()}


def _stored(store: Store, request: Mapping[str, Any]) -> dict[str, Any]:
    """A request with each file the node made itself (``ctx.out``) kept in the store."""

    def keep(value: Any) -> Any:
        if isinstance(value, Output):
            return store.put_bytes(value.data, kind=value.kind, name="request/file")
        if isinstance(value, list):
            return [keep(item) for item in value]
        if isinstance(value, dict):
            return {key: keep(item) for key, item in value.items()}
        return value

    return {key: keep(value) for key, value in request.items()}


def _request_identity(request: Mapping[str, Any]) -> Any:
    def encode(value: Any) -> Any:
        if isinstance(value, Output):
            import hashlib

            return {"bytes": hashlib.sha256(value.data).hexdigest(), "kind": value.kind}
        if isinstance(value, list):
            return [encode(item) for item in value]
        if isinstance(value, dict):
            return {key: encode(item) for key, item in value.items()}
        return plain(value)

    return encode(dict(request))


async def call_capability(
    services: HostServices,
    name: str,
    route: Route,
    request: Mapping[str, Any],
    *,
    take: int,
    instance_id: str,
    take_path: Sequence[int] = (),
) -> CallResult:
    """One paid call: from the call cache when an identical request was answered.

    Every call is written down before it may leave. A call whose process died while it was
    out stops the next run for a person, since nobody can say it did not bill; a long job an
    interrupted run submitted is collected instead, never submitted again.

    A call is keyed by its take: a number, or inside a group that regenerates, every take on
    the way to it, so the group's next take asks again instead of reading the last answer.
    """

    store = services.store
    key = store.call_key(
        capability=name,
        route=route.fingerprint,
        request=_request_identity(request),
        take=list(take_path) if len(take_path) > 1 else take,
    )
    cached = store.load_call(key)
    if cached is not None:
        store.clear_job(key)
        _record(services, instance_id, name, route, key, cached=True, cost=0.0)
        return _call_result(store, cached, cached=True)
    if not services.live:
        raise CapabilityError(f"{name} on {route.route_id} is a paid call; run with --live")
    handler = services.capabilities.get(name)
    if handler is None:
        raise CapabilityError(f"no provider adapter serves {name} on {route.route_id}")
    staged = {
        key_: (
            store.put_bytes(value.data, kind=value.kind, name=key_)
            if isinstance(value, Output)
            else value
        )
        for key_, value in request.items()
    }
    job = store.load_job(key)
    if job is not None:
        if job.state != "submitted" or job.handle is None or not isinstance(handler, LongJob):
            raise CapabilityError(
                f"{name} on {route.route_id} (take {take}) was being submitted when a run "
                "stopped, and nobody can say whether the provider took it. Check the "
                f"provider's dashboard, then run `gnode jobs forget {key}` to submit it again"
            )
        # Its hold was charged by the run that submitted it; collecting bills nothing new.
        log = JobLog(store, key, name, route.route_id, take)
        record = await handler.collect(route, staged, take, job.handle, log)
        store.save_call(key, record)
        store.clear_job(key)
        _record(services, instance_id, name, route, key, cached=False, cost=record.cost_usd)
        return _call_result(store, record, cached=False)
    _, high = route.cost(request)
    hold = (
        await services.spending.reserve(instance_id, high)
        if services.spending is not None
        else None
    )
    log = JobLog(store, key, name, route.route_id, take)
    try:
        if isinstance(handler, LongJob):
            record = await handler.start(route, staged, take, log)
        else:
            log.submitting()
            record = await handler(route, staged, take)
    except CallRefused:
        store.clear_job(key)
        if services.spending is not None and hold is not None:
            services.spending.settle(hold, 0.0)
        raise
    except Exception:
        # The handler answered, with a failure: the call is over, whatever it billed. A long
        # job says itself whether anything of it is left to collect.
        if not isinstance(handler, LongJob):
            store.clear_job(key)
        if services.spending is not None and hold is not None:
            services.spending.settle(hold, None)
        raise
    except BaseException:
        # Interrupted mid-call: it stays written down, and its whole hold stays charged.
        if services.spending is not None and hold is not None:
            services.spending.settle(hold, None)
        raise
    if services.spending is not None and hold is not None:
        services.spending.settle(hold, record.cost_usd)
    store.save_call(key, record)
    store.clear_job(key)
    _record(services, instance_id, name, route, key, cached=False, cost=record.cost_usd)
    return _call_result(store, record, cached=False)


def _record(
    services: HostServices,
    instance_id: str,
    name: str,
    route: Route,
    key: str,
    *,
    cached: bool,
    cost: float | None,
) -> None:
    if services.on_call is not None:
        services.on_call(
            {
                "id": instance_id,
                "capability": name,
                "route": route.route_id,
                "call": key,
                "cached": cached,
                "cost_usd": cost,
            }
        )


def _call_result(store: Store, record: CallRecord, *, cached: bool) -> CallResult:
    files = {
        name: InputFile(
            path=store.file_path(file.digest),
            kind=file.kind,
            digest=file.digest,
            key=file.key,
            value=file,
        )
        for name, file in record.files.items()
    }
    return CallResult(files, record.data, record.cost_usd, cached)


# ------------------------------------------------------------------------- execute


def _stage(store: Store, value: Any) -> Any:
    if isinstance(value, FileValue):
        if not store.has(value) and value.location is not None:
            store.put_file(Path(value.location), kind=value.kind, name=value.name)
        return InputFile(store.file_path(value.digest), value.kind, value.digest, value.key, value)
    if isinstance(value, Collection):
        return {key: _stage(store, item) for key, item in value.items}
    if isinstance(value, list):
        return [_stage(store, item) for item in value]
    if isinstance(value, dict):  # a map of files from the inputs, given to a keyed port
        return {key: _stage(store, item) for key, item in value.items()}
    return value


def _param_value(value: Any) -> Any:
    if isinstance(value, FileValue):
        return value.content if value.content is not None else value
    if isinstance(value, Collection):
        return {key: _param_value(item) for key, item in value.items}
    if isinstance(value, list):
        return [_param_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _param_value(item) for key, item in value.items()}
    if value is MISSING:
        return None
    return value


def read_set(instance: Instance) -> dict[str, str]:
    """The digests of every file an instance reads: what its cached result must match."""

    found: dict[str, str] = {}
    for name, value in instance.with_.items():
        for index, file in enumerate(files_in(value)):
            found[f"{name}/{index}"] = file.digest
    return found


async def execute(
    instance: Instance,
    *,
    services: HostServices,
    project_root: Path,
) -> Result:
    """Run one instance whose inputs all exist; validate and store what it returns."""

    spec = instance.spec
    store = services.store
    if instance.identity is not None:
        cached = store.load_result(instance.identity, read=read_set(instance))
        if cached is not None:
            outputs, facts = cached
            return Result("succeeded", outputs, {**facts, "cached": True})
    if instance.native:
        return _select(instance)
    # An optional input that does not exist (its step did not run, or the workflow input
    # was not given) is not among the inputs.
    inputs = {
        name: _stage(store, instance.with_[name])
        for name in spec.inputs
        if name in instance.with_ and not expr.is_nothing(instance.with_[name])
    }
    params = {
        name: _param_value(instance.with_[name]) for name in spec.params if name in instance.with_
    }
    work_root = services.work_root or Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=_ensure(work_root), prefix="node-") as work:
        ctx = Ctx(
            instance,
            inputs=inputs,
            params=params,
            services=services,
            project_root=project_root,
            work_dir=Path(work),
        )
        try:
            if spec.capability is not None and spec.body is None:
                returned = await _capability_node(ctx, spec)
            elif spec.body is None:
                raise NodeFailure(f"{instance.uses} has no implementation yet")
            elif inspect.iscoroutinefunction(spec.body):
                returned = await spec.body(ctx)
            else:
                returned = await asyncio.to_thread(spec.body, ctx)
        except NodeFailure as failure:
            return Result("failed", {}, ctx.facts, str(failure))
        outputs = _accept(instance, ctx, returned)
    if spec.judge and ctx.facts.get("verdict") not in {"accept", "reject"}:
        return Result("failed", {}, ctx.facts, f"{spec.name} is a judge and reported no verdict")
    facts = {**ctx.facts}
    if ctx.calls:
        facts.setdefault("cost_usd", round(ctx.cost_usd, 6))
    if instance.identity is not None:
        store.save_result(
            instance.identity,
            type_identity=instance.type_identity,
            outputs=outputs,
            facts=ctx.facts,
            read=read_set(instance),
            cost_usd=ctx.cost_usd if ctx.calls else None,
        )
    return Result("succeeded", outputs, facts)


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _capability_node(ctx: Ctx, spec: NodeSpec) -> dict[str, Any]:
    """A built-in paid type: one call with its settings and inputs, its files as outputs."""

    assert spec.capability is not None
    # ``vars`` only feeds the prompt templates, which the expander has already rendered.
    request = {**{k: v for k, v in ctx.params.items() if k != "vars"}, **ctx.inputs}
    result = await ctx.capability(spec.capability, **request)
    outputs: dict[str, Any] = {}
    for name, port in spec.outputs.items():
        file = result.files.get(name) or next(
            (f for f in result.files.values() if f.kind.split("/", 1)[0] == port.family), None
        )
        if file is not None:
            outputs[name] = Output(file.read_bytes(), file.kind)
    if isinstance(result.data, Mapping):
        verdict = result.data.get("verdict")
        if isinstance(verdict, str):
            ctx.fact("verdict", verdict)
        for name, value in result.data.get("facts", {}).items():
            ctx.fact(name, value)
        if "json" in spec.outputs and "json" not in outputs:
            outputs["json"] = ctx.out.json(result.data.get("json", result.data))
    return outputs


def _accept(instance: Instance, ctx: Ctx, returned: Any) -> dict[str, Any]:
    spec = instance.spec
    if returned is None:
        returned = {}
    if not isinstance(returned, Mapping):
        raise NodeFailure(f"{spec.name} returned {type(returned).__name__}, not its outputs")
    returned = dict(returned)
    if "annotations" in spec.outputs and "annotations" not in returned and ctx.marks:
        returned["annotations"] = ctx.out.json({"kind": ANNOTATIONS_KIND, "annotations": ctx.marks})
    unknown = sorted(set(returned) - set(spec.outputs))
    if unknown:
        raise NodeFailure(f"{spec.name} returned undeclared outputs {unknown}")
    outputs: dict[str, Any] = {}
    for name, port in spec.outputs.items():
        value = returned.get(name)
        if value is None:
            if not port.optional:
                raise NodeFailure(f"{spec.name} did not return its output {name}")
            continue
        outputs[name] = _store_output(ctx._services.store, instance, name, port.shape, value)
    return outputs


def _store_output(store: Store, instance: Instance, name: str, shape: str, value: Any) -> Any:
    def one(item: Any, label: str, key: str | None = None) -> FileValue:
        if isinstance(item, InputFile):
            return item.value.with_key(key)
        if not isinstance(item, Output):
            raise NodeFailure(f"output {label} is {type(item).__name__}; use ctx.out to make it")
        return store.put_bytes(item.data, kind=item.kind, name=f"{instance.path}/{label}", key=key)

    if shape == "list":
        if not isinstance(value, list):
            raise NodeFailure(f"output {name} is a list")
        return [one(item, f"{name}[{index}]") for index, item in enumerate(value)]
    if shape == "keyed":
        if not isinstance(value, Mapping):
            raise NodeFailure(f"output {name} is a keyed collection")
        return Collection(
            tuple((key, one(item, f"{name}[{key}]", key)) for key, item in value.items())
        )
    return one(value, name)


def _select(instance: Instance) -> Result:
    """``gnode/select``: the first candidate that exists and was not rejected."""

    candidates = instance.with_.get("first_of", [])
    for candidate in candidates if isinstance(candidates, list) else []:
        if candidate is MISSING or candidate is None or type(candidate).__name__ == "Failed":
            continue
        return Result("succeeded", {"value": candidate}, {"chosen": candidates.index(candidate)})
    return Result("skipped", {}, {}, "no candidate exists")


__all__ = [
    "ANNOTATIONS_KIND",
    "Agent",
    "CallRefused",
    "CallResult",
    "CapabilityError",
    "CapabilityHandler",
    "Ctx",
    "HostServices",
    "InputFile",
    "JobLog",
    "LongJob",
    "NodeFailure",
    "Output",
    "Spending",
    "call_capability",
    "execute",
    "read_set",
    "register_reader",
    "register_writer",
    "render_template",
    "tool",
]
