# 技术规范：基于 AutoGen + Magenta 的多智能体音乐共创系统

**版本**: 1.0
**日期**: 2026-04-12
**状态**: 待审阅（已完成自审）

---

## 1. 目标与范围

### 1.1 本文档涵盖的内容
本规范定义以下三个子系统的完整技术设计：
1. **AutoGen Agent 层重构** — 将自定义 Agent 替换为 AutoGen v0.7.5 agentchat 体系
2. **Magenta 音乐引擎集成** — 独立微服务 + 可插拔抽象接口
3. **多 LLM 后端支持** — Ollama / OpenAI / Claude / DeepSeek / Gemini 统一客户端

### 1.2 不涉及的内容
- ReaImGui DAW 内嵌 UI 的具体界面设计（后续阶段）
- VST 插件的具体参数映射表（后续阶段）
- 用户鉴权与权限管理（本系统为单用户本地应用）

### 1.3 成功标准
- 用户输入一段文字描述，系统自动输出可在 Reaper 中打开编辑的多轨 MIDI 文件
- Agent 对话可追溯，每轮修改有据可查
- Magenta 引擎可在不修改 Agent 代码的前提下替换为其他模型
- 至少支持 2 种 LLM 后端同时可用

---

## 2. 架构总览

### 2.1 进程拓扑

```
┌─────────────────────────────────────────────────────┐
│                 主进程 (Python 3.10+)                 │
│                                                       │
│  FastAPI (端口 8000)                                  │
│    ├── /api/generate          REST 同步生成            │
│    ├── /api/generate/async    异步任务提交             │
│    ├── /api/jobs/{id}         任务状态查询             │
│    └── /ws/generate           WebSocket 实时进度       │
│                                                       │
│  AutoGen Runtime                                      │
│    └── SelectorGroupChat                              │
│         ├── OrchestratorAgent                         │
│         ├── ComposerAgent                             │
│         ├── LyricistAgent                             │
│         ├── InstrumentalistAgent                      │
│         ├── CriticAgent                               │
│         └── SynthesizerAgent ──HTTP──┐                │
│                                      │                │
│  LLM Client (多后端)                 │                │
│    ├── OllamaBackend                 │                │
│    ├── OpenAIBackend                 │                │
│    ├── ClaudeBackend                 │                │
│    ├── DeepSeekBackend               │                │
│    └── GeminiBackend                 │                │
└──────────────────────────────────────┼────────────────┘
                                       │
                              HTTP localhost:8001
                                       │
┌──────────────────────────────────────┼────────────────┐
│           Magenta 微服务 (Python 3.7, conda)          │
│                                                       │
│  FastAPI (端口 8001)                                  │
│    ├── POST /generate_melody       attention_rnn      │
│    ├── POST /generate_polyphony    polyphony_rnn      │
│    ├── GET  /health                                   │
│    └── GET  /models                                   │
│                                                       │
│  预训练模型:                                          │
│    ├── models/attention_rnn.mag                       │
│    └── models/polyphony_rnn.mag                       │
└───────────────────────────────────────────────────────┘
```

### 2.2 数据流全景

```
User Request (JSON)
       │
       ▼
  ┌─────────┐       阶段一: 创意框架
  │Orchestr. │──→ Composition Blueprint
  └────┬────┘
       │
  ┌────┴────┐
  ▼         ▼
Composer  Lyricist ──→ Blueprint 填充 (和弦/旋律轮廓/歌词/primer notes)
  │         │
  └────┬────┘
       │
       ▼
  ┌───────────┐     阶段二: 草稿生成
  │Synthesizer│──HTTP──→ Magenta ──→ Draft Score (NoteSequence → Score JSON)
  └─────┬─────┘
        │
        ▼
  ┌─── SelectorGroupChat ──┐   阶段三: 迭代精修
  │                         │
  │  Critic ──→ 评审        │
  │  Composer ──→ 改音符    │
  │  Lyricist ──→ 对齐歌词  │
  │  Instrumentalist ──→ 配器│
  │  Critic ──→ 再评审      │
  │                         │
  │  [灵感重置?]            │
  │    └→ Synthesizer ──→ Magenta (重新生成变体)
  │       └→ 评分/选择/嫁接  │
  │                         │
  └────────┬────────────────┘
           │
           ▼
     Finalized Score
           │
     ┌─────┴─────┐
     ▼           ▼
  MIDI 文件   Reaper DAW
  (output/)   (自动导入)
```

---

## 3. 子系统一：AutoGen Agent 层

### 3.1 依赖关系

主进程依赖 `autogen-agentchat` 和 `autogen-core` 包。源码已克隆于 `./autogen/`，以 editable 模式安装：

```bash
pip install -e ./autogen/python/packages/autogen-core
pip install -e ./autogen/python/packages/autogen-agentchat
```

### 3.2 Agent 定义

所有 Agent 继承 `autogen_agentchat.agents.BaseChatAgent`，必须实现：
- `produced_message_types` — 该 Agent 能产出的消息类型
- `on_messages(messages, cancellation_token) → Response` — 核心处理逻辑
- `on_reset(cancellation_token)` — 重置状态

#### 3.2.1 OrchestratorAgent

**职责**：解析用户自然语言输入，生成结构化的 Composition Blueprint。

**输入消息**：`TextMessage` (用户描述) 或 `StructuredMessage[MusicRequest]`

**输出消息**：`StructuredMessage[CompositionBlueprint]`

**内部行为**：
1. 调用 LLM，传入用户描述 + 系统提示词
2. LLM 返回 JSON 格式的 Blueprint
3. 验证 Blueprint 完整性（调性/拍号/段落必须存在），缺失字段用合理默认值填充
4. 包装为 `CompositionBlueprint` 返回

**状态**：保留当前 Blueprint 以便后续修改。

#### 3.2.2 ComposerAgent

**职责**：设计和弦进行、旋律轮廓；在迭代精修阶段直接编辑 Score 中的音符。

**输入消息**：
- 阶段一：`StructuredMessage[CompositionBlueprint]` → 填充和弦与旋律轮廓
- 阶段三：`StructuredMessage[ScoreWithFeedback]` → 按反馈修改具体音符

**输出消息**：`StructuredMessage[ScoreUpdate]`

**内部行为（阶段三）**：
1. 接收 Critic 反馈 + 当前 Score JSON
2. 调用 LLM，提示词包含："这是当前乐谱的第 N 小节音符序列 [...], Critic 反馈为 [...], 请给出具体的音符修改指令"
3. LLM 返回结构化的修改指令（增/删/改音符，调整力度/时值）
4. 将修改指令应用到 Score 对象上
5. 返回更新后的 Score

**灵感重置权限**：Composer 可在输出中附加 `request_regeneration: true` 标记，触发 Synthesizer 重新调用 Magenta。

#### 3.2.3 LyricistAgent

**职责**：创作歌词，确保音节数与旋律节拍对齐。

**输入消息**：
- 阶段一：`StructuredMessage[CompositionBlueprint]` → 写歌词
- 阶段三：`StructuredMessage[ScoreWithLyrics]` → 根据修改后的旋律重新对齐音节

**输出消息**：`StructuredMessage[LyricsUpdate]`

**内部行为**：
1. 从 Score 中提取每个段落的节拍数和旋律重音位置
2. 调用 LLM 生成/修改歌词，约束条件为每行音节数
3. 返回带有 beat-aligned syllables 的歌词

**条件参与**：仅在 `include_lyrics == true` 时参与 GroupChat。

#### 3.2.4 InstrumentalistAgent

**职责**：分配乐器和 MIDI 通道、配置 VST 插件、注入东方乐器的 Pitch Bend / Expression 自动化。

**输入消息**：`StructuredMessage[ScoreUpdate]` — 接收接近最终的 Score

**输出消息**：`StructuredMessage[InstrumentationPlan]`

**内部行为**：
1. 根据 Score 中的乐器列表和音域范围，分配 MIDI 通道和 GM Program Number
2. 对东方乐器（古筝/二胡/琵琶/笛子），调用 LLM 判断哪些音符需要弯音/滑音/轮指，注入对应的 Pitch Bend 和 CC 数据
3. 输出每条轨道的 VST 插件名称、预设、Articulation 映射

**东方乐器知识**（硬编码于 Agent 内部）：

| 乐器 | 典型 VST | 特殊技法 | MIDI 实现 |
|:---|:---|:---|:---|
| 古筝 | Kong Audio ChineeGuzheng | 刮奏、按弦 | Pitch Bend (±4半音) + CC11 |
| 二胡 | Kong Audio ChineeErhu | 滑音、揉弦 | Pitch Bend (±2半音) + CC1 Vibrato |
| 琵琶 | Kong Audio ChineePipa | 轮指、弯弦 | CC11 Tremolo + Pitch Bend |
| 笛子 | Kong Audio ChineeDizi | 花舌、颤音 | CC2 Breath + Trill 音符 |

#### 3.2.5 CriticAgent

**职责**：审查 Score 质量，给出结构化评分和修改指令。

**输入消息**：`StructuredMessage[Score]` + 原始 MusicRequest

**输出消息**：`StructuredMessage[CriticReview]`

**CriticReview 结构**：
```python
class CriticReview(BaseModel):
    overall_score: float          # 0.0 - 1.0
    passes: bool                  # score >= threshold
    aspect_scores: dict[str, float]  # harmony, melody, rhythm, lyrics, arrangement
    issues: list[CriticIssue]     # 具体问题列表
    request_regeneration: bool    # 是否建议灵感重置
    revision_instructions: str    # 给 Composer 的修改指令
```

**评分维度**：
- **和声 (harmony)**: 和弦进行是否流畅、调性是否统一
- **旋律 (melody)**: 音域是否合理、是否有不自然的大跳
- **节奏 (rhythm)**: 节拍是否稳定、密度是否匹配风格
- **歌词 (lyrics)**: 音节对齐、押韵一致性
- **编曲 (arrangement)**: 乐器平衡、频率空间冲突

**灵感重置触发条件**：连续 2 轮 `overall_score < 0.5`。

#### 3.2.6 SynthesizerAgent

**职责**：桥接 Magenta 微服务。调用 Magenta API 生成 MIDI，解析 NoteSequence 转化为 Score JSON。

**输入消息**：
- `StructuredMessage[SynthesisRequest]` — 包含 primer_notes, num_steps, temperature, qpm, model_type ("melody" | "polyphony")

**输出消息**：`StructuredMessage[DraftScore]`

**内部行为**：
1. 通过 `httpx` 调用 `http://localhost:8001/generate_melody` 或 `/generate_polyphony`
2. 接收返回的 MIDI 文件路径
3. 用 `mido` 读取 MIDI 文件，解析为 Score 内部表示
4. 返回 DraftScore

**错误处理**：
- Magenta 服务不可用 → 返回错误消息，GroupChat 继续用纯 LLM 模式
- 生成超时 → 重试一次，仍失败则降级

**无 LLM 调用**：此 Agent 不使用 LLM，纯粹是 HTTP 客户端 + MIDI 解析器。

### 3.3 GroupChat 编排

使用 `SelectorGroupChat`，LLM 根据当前对话上下文选择下一个 speaker。

```python
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination

team = SelectorGroupChat(
    participants=[orchestrator, composer, lyricist, instrumentalist, critic, synthesizer],
    model_client=llm_client,
    termination_condition=(
        TextMentionTermination("FINALIZED")
        | MaxMessageTermination(max_messages=50)
    ),
    selector_prompt=SELECTOR_PROMPT,
    allow_repeated_speaker=True,  # Critic 可能需要连续发言
)
```

**Selector Prompt 策略**：

```
你是一个音乐创作团队的调度员。根据当前对话进度选择下一个发言的 Agent。

规则：
1. 对话开始时，总是选择 orchestrator
2. orchestrator 完成 Blueprint 后，选择 composer 和 lyricist 填充细节
3. Blueprint 完成后，选择 synthesizer 调用 Magenta 生成草稿
4. 草稿生成后，进入精修循环：critic → composer → lyricist → instrumentalist → critic
5. 如果任何 Agent 请求灵感重置 (request_regeneration)，选择 synthesizer
6. 当 critic 评分 >= 0.8 且标记 passes=true 时，选择 instrumentalist 做最终配器
7. instrumentalist 完成后，输出 "FINALIZED" 结束对话

可用 Agent：{agent_names}
当前对话历史中最后一条消息来自：{last_speaker}
```

**阶段感知**：GroupChat 不需要显式的阶段切换逻辑，SelectorGroupChat 通过 LLM 理解对话上下文自动推进阶段。三阶段的推进完全依赖 Selector Prompt 的规则和对话历史。

### 3.4 消息类型

基于 AutoGen 的 `BaseChatMessage` 和 `StructuredMessage` 机制定义：

```python
from autogen_agentchat.messages import StructuredMessage, TextMessage

# Blueprint 消息
class CompositionBlueprint(BaseModel):
    title: str
    key: str
    scale_type: str
    tempo: int
    time_signature: list[int]
    sections: list[SectionPlan]
    instruments: list[InstrumentPlan]
    lyrics_plan: LyricsPlan
    primer_notes: list[int]
    primer_temperature: float

# Score 消息 — Agent 直接操作的核心对象
class ScoreData(BaseModel):
    sections: list[ScoreSection]
    tracks: list[ScoreTrack]
    metadata: dict

# Critic 评审消息
class CriticReview(BaseModel):
    overall_score: float
    passes: bool
    aspect_scores: dict[str, float]
    issues: list[CriticIssue]
    request_regeneration: bool
    revision_instructions: str

# Synthesis 请求
class SynthesisRequest(BaseModel):
    primer_notes: list[int]
    num_steps: int
    temperature: float
    qpm: float
    model_type: str  # "melody" | "polyphony"
    section_name: str | None = None

# Blueprint 子结构
class SectionPlan(BaseModel):
    name: str                # intro, verse, chorus, bridge, outro
    bars: int
    chords_per_bar: int = 1
    mood: str = ""
    dynamics: str = "mf"     # pp, p, mp, mf, f, ff

class InstrumentPlan(BaseModel):
    name: str
    role: str                # lead, bass, drums, accompaniment, pad
    style_notes: str = ""

class LyricsPlan(BaseModel):
    include: bool = False
    language: str = "en"
    theme: str = ""
    syllable_density: str = "moderate"  # sparse, moderate, dense

# Critic 子结构
class CriticIssue(BaseModel):
    aspect: str              # harmony, melody, rhythm, lyrics, arrangement
    location: str            # e.g. "chorus, bar 3-4" or "lead track, beat 12-16"
    severity: str            # minor, moderate, major
    description: str
    suggestion: str

# Score 修改指令 (Composer 输出)
class NoteEdit(BaseModel):
    action: str              # "add", "delete", "modify"
    track: str
    section: str
    target_beat: float | None = None       # for delete/modify: which note to target
    pitch: int | None = None
    start_beat: float | None = None
    duration_beats: float | None = None
    velocity: int | None = None

class ScoreUpdate(BaseModel):
    edits: list[NoteEdit]
    request_regeneration: bool = False
    commentary: str = ""     # Composer 对修改的解释

# Lyrics 更新
class LyricsUpdate(BaseModel):
    section_name: str
    lines: list[dict]        # [{text, syllable_count, start_beat}]
    rhyme_scheme: str = ""

# Instrumentation 输出
class InstrumentationPlan(BaseModel):
    tracks: list[dict]       # [{instrument, channel, program, vst_plugin, articulations, ...}]
    mixing_notes: str = ""
```

---

## 4. 子系统二：Magenta 音乐引擎

### 4.1 抽象接口

```python
# src/engine/interface.py
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel

class GenerationRequest(BaseModel):
    primer_notes: list[int]
    num_steps: int = 128
    temperature: float = 1.0
    qpm: float = 120.0

class GenerationResult(BaseModel):
    midi_path: Path
    notes: list[dict]  # [{pitch, start_time, end_time, velocity}, ...]
    duration_seconds: float

class MusicEngineInterface(ABC):
    @abstractmethod
    async def generate_melody(self, request: GenerationRequest) -> GenerationResult:
        """生成单声部旋律。"""
        ...

    @abstractmethod
    async def generate_polyphony(self, request: GenerationRequest) -> GenerationResult:
        """生成多声部和声。"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
```

### 4.2 Magenta 实现

```python
# src/engine/magenta_engine.py
class MagentaEngine(MusicEngineInterface):
    """通过 HTTP 调用独立运行的 Magenta 微服务。"""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self._http = httpx.AsyncClient(timeout=60.0)

    async def generate_melody(self, request: GenerationRequest) -> GenerationResult:
        resp = await self._http.post(
            f"{self.base_url}/generate_melody",
            json=request.model_dump(),
        )
        resp.raise_for_status()
        return GenerationResult(**resp.json())

    async def generate_polyphony(self, request: GenerationRequest) -> GenerationResult:
        resp = await self._http.post(
            f"{self.base_url}/generate_polyphony",
            json=request.model_dump(),
        )
        resp.raise_for_status()
        return GenerationResult(**resp.json())

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._http.aclose()
```

### 4.3 Magenta 微服务

独立的 FastAPI 应用，运行在 conda `magenta_env` (Python 3.7) 中。

```python
# src/engine/magenta_service.py (运行于独立进程)
import magenta.music as mm
from magenta.models.melody_rnn import melody_rnn_sequence_generator
from magenta.models.polyphony_rnn import polyphony_rnn_sequence_generator
from magenta.models.shared import sequence_generator_bundle
from magenta.protobuf import generator_pb2
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Magenta Music Engine")

# 模型加载 (启动时执行一次)
melody_bundle = sequence_generator_bundle.read_bundle_file('./models/attention_rnn.mag')
melody_gen_map = melody_rnn_sequence_generator.get_generator_map()
melody_generator = melody_gen_map['attention_rnn'](checkpoint=None, bundle=melody_bundle)
melody_generator.initialize()

poly_bundle = sequence_generator_bundle.read_bundle_file('./models/polyphony_rnn.mag')
poly_gen_map = polyphony_rnn_sequence_generator.get_generator_map()
poly_generator = poly_gen_map['polyphony'](checkpoint=None, bundle=poly_bundle)
poly_generator.initialize()

class GenRequest(BaseModel):
    primer_notes: list
    num_steps: int = 128
    temperature: float = 1.0
    qpm: float = 120.0

@app.post("/generate_melody")
def generate_melody(req: GenRequest):
    primer = _build_primer(req.primer_notes, req.qpm)
    options = _build_options(primer, req.num_steps, req.temperature, req.qpm)
    result = melody_generator.generate(primer, options)
    path = _save_midi(result, "melody")
    notes = _extract_notes(result)
    return {"midi_path": str(path), "notes": notes, "duration_seconds": result.total_time}

@app.post("/generate_polyphony")
def generate_polyphony(req: GenRequest):
    primer = _build_primer(req.primer_notes, req.qpm)
    options = _build_options(primer, req.num_steps, req.temperature, req.qpm)
    result = poly_generator.generate(primer, options)
    path = _save_midi(result, "polyphony")
    notes = _extract_notes(result)
    return {"midi_path": str(path), "notes": notes, "duration_seconds": result.total_time}

@app.get("/health")
def health():
    return {"status": "ok", "models": ["attention_rnn", "polyphony_rnn"]}

def _build_primer(notes: list, qpm: float) -> mm.NoteSequence:
    seq = mm.NoteSequence()
    seq.tempos.add(qpm=qpm)
    t = 0.0
    step = 60.0 / qpm  # quarter note duration
    for pitch in notes:
        seq.notes.add(pitch=pitch, start_time=t, end_time=t + step, velocity=80)
        t += step
    seq.total_time = t
    return seq

def _build_options(primer, num_steps, temperature, qpm):
    options = generator_pb2.GeneratorOptions()
    options.args['temperature'].float_value = temperature
    step_duration = 60.0 / qpm / 4  # 16th note
    start = primer.total_time
    end = start + num_steps * step_duration
    options.generate_sections.add(start_time=start, end_time=end)
    return options

def _save_midi(sequence, prefix):
    import os, time
    os.makedirs("./output/drafts", exist_ok=True)
    path = f"./output/drafts/{prefix}_{int(time.time())}.mid"
    mm.sequence_proto_to_midi_file(sequence, path)
    return path

def _extract_notes(sequence):
    return [
        {"pitch": n.pitch, "start_time": n.start_time,
         "end_time": n.end_time, "velocity": n.velocity}
        for n in sequence.notes
    ]
```

### 4.4 未来替换路径

当 Magenta 需要替换时，只需实现新的 `MusicEngineInterface` 子类：

```python
# 未来: src/engine/musiclang_engine.py
class MusicLangEngine(MusicEngineInterface):
    async def generate_melody(self, request):
        from musiclang_predict import MusicLangPredictor
        # ... 使用 MusicLang API 生成 ...

# 未来: src/engine/midi_llm_engine.py
class MidiLLMEngine(MusicEngineInterface):
    async def generate_melody(self, request):
        # ... 调用 MIDI-LLM 的 vLLM 端点 ...
```

在 `config/settings.py` 中切换：
```python
music_engine: str = "magenta"  # "magenta" | "musiclang" | "midi_llm"
```

---

## 5. 子系统三：多 LLM 后端

### 5.1 统一接口

AutoGen v0.7.5 自带 `ChatCompletionClient` 协议。我们为每种后端实现一个工厂函数。

```python
# src/llm/client.py
from autogen_core.models import ChatCompletionClient

def create_llm_client(backend: str, **kwargs) -> ChatCompletionClient:
    if backend == "ollama":
        return create_ollama_client(**kwargs)
    elif backend == "openai":
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(model=kwargs.get("model", "gpt-4o"), api_key=kwargs["api_key"])
    elif backend == "claude":
        return create_claude_client(**kwargs)
    elif backend == "deepseek":
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(
            model=kwargs.get("model", "deepseek-chat"),
            api_key=kwargs["api_key"],
            base_url="https://api.deepseek.com/v1",
        )
    elif backend == "gemini":
        return create_gemini_client(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")
```

### 5.2 Ollama 适配

Ollama 的 API 与 OpenAI 格式兼容（`/v1/chat/completions`）。使用 AutoGen 的 `OpenAIChatCompletionClient` 指向 Ollama 地址：

```python
def create_ollama_client(model: str = "qwen2.5:14b", base_url: str = "http://localhost:11434") -> ChatCompletionClient:
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    return OpenAIChatCompletionClient(
        model=model,
        api_key="ollama",  # Ollama 不需要真正的 key
        base_url=f"{base_url}/v1",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )
```

### 5.3 Claude 适配

Anthropic API 格式与 OpenAI 不同，需要专门的适配器：

```python
def create_claude_client(model: str = "claude-sonnet-4-20250514", api_key: str = "") -> ChatCompletionClient:
    # 优先检查 autogen-ext 是否提供 Anthropic 扩展
    try:
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient
        return AnthropicChatCompletionClient(model=model, api_key=api_key)
    except ImportError:
        # 降级方案：通过 LiteLLM 代理统一为 OpenAI 格式
        # 需安装 litellm: pip install litellm
        # 启动代理: litellm --model anthropic/claude-sonnet-4-20250514 --port 4000
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(
            model=model,
            api_key=api_key,
            base_url="http://localhost:4000/v1",
        )
```

### 5.4 Gemini 适配

```python
def create_gemini_client(model: str = "gemini-pro", api_key: str = "") -> ChatCompletionClient:
    # Google Gemini 通过 OpenAI 兼容端点调用
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
```

### 5.5 配置

```python
# config/settings.py 新增字段
class Settings(BaseSettings):
    # LLM
    llm_backend: str = "ollama"  # ollama | openai | claude | deepseek | gemini
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = ""
    llm_base_url: str | None = None

    # Ollama (当 llm_backend == "ollama")
    ollama_base_url: str = "http://localhost:11434"

    # Music Engine
    music_engine: str = "magenta"
    magenta_url: str = "http://localhost:8001"
```

---

## 6. Score 数据结构 — Agent 直接编辑的核心对象

### 6.1 设计原则

Score 是整个迭代精修阶段的"共享白板"。所有 Agent 读取和修改的都是同一个 Score 对象。它必须：
- 足够紧凑，可以序列化为 JSON 放在 LLM 上下文中
- 包含音符级别的细节，但也能概括为高层摘要
- 支持局部替换（嫁接 Magenta 重新生成的片段）

### 6.2 结构定义

```python
# src/music/score.py

class ScoreNote(BaseModel):
    pitch: int            # MIDI 0-127
    start_beat: float     # 以拍为单位的绝对位置
    duration_beats: float
    velocity: int = 80
    articulation: str = "normal"
    pitch_bend: int | None = None
    expression: int | None = None

class ScoreSection(BaseModel):
    name: str             # intro, verse, chorus, bridge, outro
    start_beat: float
    bars: int
    chords: list[dict]    # [{root, quality, start_beat, duration_beats}]
    lyrics: list[dict] | None = None  # [{text, start_beat, duration_beats}]

class ScoreTrack(BaseModel):
    name: str
    instrument: str
    role: str             # lead, bass, drums, accompaniment, pad
    channel: int
    program: int
    notes: list[ScoreNote]
    vst_plugin: str | None = None
    vst_preset: str | None = None

class Score(BaseModel):
    title: str
    key: str
    scale_type: str
    tempo: int
    time_signature: list[int]
    sections: list[ScoreSection]
    tracks: list[ScoreTrack]
    version: int = 1      # 每次修改递增

    def to_summary(self) -> str:
        """生成紧凑的文本摘要供 LLM 阅读。"""
        lines = [f"# {self.title} | {self.key} {self.scale_type} | {self.tempo}bpm | {self.time_signature[0]}/{self.time_signature[1]}"]
        for sec in self.sections:
            chords_str = " → ".join(f"{c['root']}{c.get('quality','')}" for c in sec.chords)
            lines.append(f"## {sec.name} ({sec.bars} bars): {chords_str}")
        for trk in self.tracks:
            lines.append(f"Track [{trk.name}] ({trk.role}): {len(trk.notes)} notes, ch={trk.channel}")
        return "\n".join(lines)

    def get_section_notes(self, section_name: str, track_name: str) -> list[ScoreNote]:
        """提取特定段落+轨道的音符，用于 LLM 上下文。"""
        sec = next((s for s in self.sections if s.name == section_name), None)
        trk = next((t for t in self.tracks if t.name == track_name), None)
        if not sec or not trk:
            return []
        return [n for n in trk.notes if sec.start_beat <= n.start_beat < sec.start_beat + sec.bars * self.time_signature[0]]

    def replace_section_notes(self, section_name: str, track_name: str, new_notes: list[ScoreNote]) -> None:
        """替换特定段落+轨道的音符（灵感重置的嫁接操作）。"""
        sec = next((s for s in self.sections if s.name == section_name), None)
        trk = next((t for t in self.tracks if t.name == track_name), None)
        if not sec or not trk:
            return
        sec_start = sec.start_beat
        sec_end = sec_start + sec.bars * self.time_signature[0]
        trk.notes = [n for n in trk.notes if not (sec_start <= n.start_beat < sec_end)]
        trk.notes.extend(new_notes)
        trk.notes.sort(key=lambda n: n.start_beat)
        self.version += 1
```

### 6.3 LLM 上下文管理

完整 Score 可能过大无法放入 LLM 上下文。策略：

1. **摘要模式**：`score.to_summary()` 给 LLM 全局视图（<500 tokens）
2. **聚焦模式**：`score.get_section_notes("chorus", "lead")` 仅展示当前正在修改的段落（<2000 tokens）
3. **Critic 全量模式**：Critic 评审时看完整 Score JSON（可能较长，但只发生有限次）

---

## 7. 灵感重置机制 (Inspiration Reset)

### 7.1 触发条件

| 条件 | 触发者 | 优先级 |
|:---|:---|:---|
| Critic 连续 2 轮 `overall_score < 0.5` | CriticAgent 自动设置 `request_regeneration=true` | 高 |
| Composer 判断乐句走向不可挽救 | ComposerAgent 在输出中标记 `request_regeneration=true` | 中 |
| 用户在 DAW UI 点击"换灵感"按钮 | API 路由注入 `InspirationResetMessage` 到 GroupChat | 高 |

### 7.2 执行流程

1. SelectorGroupChat 的 Selector LLM 检测到 `request_regeneration`，选择 `SynthesizerAgent`
2. SynthesizerAgent 收到请求，根据当前 Blueprint 生成**3个变体**（temperature 分别设为 0.8, 1.0, 1.3）
3. SynthesizerAgent 将 3 个变体 Score 的摘要发送到 GroupChat
4. Selector 选择 CriticAgent 评审 3 个变体
5. CriticAgent 对每个变体打分，选出最佳变体或从多个变体中挑选最佳片段
6. 最佳变体/片段通过 `Score.replace_section_notes()` 嫁接到当前 Score
7. 精修循环继续

### 7.3 防止无限循环

- 最多触发 3 次灵感重置，之后强制使用当前最佳版本
- GroupChat 总消息数上限 50 条
- 任一 Agent 可输出 "FINALIZED" 终止 GroupChat

---

## 8. 文件结构（最终版）

```
Music_Generator/
├── autogen/                          # AutoGen v0.7.5 源码（已克隆）
├── config/
│   ├── __init__.py
│   └── settings.py                   # 全局配置 (LLM后端/Magenta地址/默认参数)
├── docs/
│   └── specs/
│       └── 2026-04-12-multi-agent-music-system-design.md  ← 本文件
├── models/                           # Magenta 预训练模型
│   ├── attention_rnn.mag
│   └── polyphony_rnn.mag
├── src/
│   ├── __init__.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # OrchestratorAgent(BaseChatAgent)
│   │   ├── composer.py               # ComposerAgent(BaseChatAgent)
│   │   ├── lyricist.py               # LyricistAgent(BaseChatAgent)
│   │   ├── instrumentalist.py        # InstrumentalistAgent(BaseChatAgent)
│   │   ├── critic.py                 # CriticAgent(BaseChatAgent)
│   │   ├── synthesizer.py            # SynthesizerAgent(BaseChatAgent) — Magenta 桥接
│   │   └── pipeline.py               # SelectorGroupChat 初始化 + 运行入口
│   ├── music/
│   │   ├── __init__.py
│   │   ├── models.py                 # Pydantic 数据模型 (MusicRequest, InstrumentRequest 等)
│   │   ├── score.py                  # Score / ScoreNote / ScoreSection / ScoreTrack
│   │   ├── theory.py                 # 音阶、和弦、调式工具函数
│   │   └── midi_writer.py            # Score → MIDI 文件转换
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── interface.py              # MusicEngineInterface (ABC)
│   │   ├── magenta_engine.py         # MagentaEngine — HTTP 客户端
│   │   └── magenta_service.py        # Magenta FastAPI 微服务 (独立进程, Python 3.7)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py                 # create_llm_client() 工厂 + 各后端适配
│   │   └── prompts.py                # Agent 系统提示词 + Selector Prompt
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py                # API 请求/响应 Pydantic 模型
│   │   └── routes.py                 # FastAPI 路由
│   ├── daw/
│   │   ├── __init__.py
│   │   └── reaper.py                 # Reaper DAW HTTP 控制客户端
│   └── main.py                       # FastAPI app 入口
├── output/
│   └── drafts/                       # Magenta 生成的草稿 MIDI
├── requirements.txt
└── Project.md
```

---

## 9. 实施顺序

以下为建议的实施顺序，每个步骤产出可独立验证的结果：

### Step 1: AutoGen Agent 层重构
1. 安装 autogen-core + autogen-agentchat (editable mode)
2. 删除旧的 `src/agents/base.py`（自定义 Agent 基类）
3. 实现 6 个 `BaseChatAgent` 子类（先用简单的 echo 逻辑验证 GroupChat 通路）
4. 实现 `pipeline.py` 中的 `SelectorGroupChat` 初始化
5. 验证：运行 GroupChat，观察 Agent 按预期顺序发言

### Step 2: Score 数据结构 + LLM 提示词
1. 实现 `src/music/score.py`
2. 编写各 Agent 的系统提示词（prompts.py）
3. 实现 Agent 的真实 `on_messages` 逻辑（调用 LLM，解析 JSON，操作 Score）
4. 验证：纯 LLM 模式下（无 Magenta），Agent 能生成 Blueprint 并进行纯文本迭代

### Step 3: Magenta 引擎集成
1. 创建 conda 环境，安装 Magenta
2. 实现 `magenta_service.py`，下载 .mag 模型
3. 实现 `MusicEngineInterface` + `MagentaEngine`
4. 实现 `SynthesizerAgent` 的 `on_messages` 逻辑
5. 验证：SynthesizerAgent 能调用 Magenta 并返回 DraftScore

### Step 4: 多 LLM 后端
1. 实现 `create_llm_client()` 工厂函数
2. 测试 Ollama + OpenAI 两种后端
3. 添加 Claude / DeepSeek / Gemini 支持
4. 验证：切换 `settings.llm_backend` 后 Agent 行为一致

### Step 5: 三阶段管线闭环
1. 将 Step 1-4 串联，实现完整的三阶段流程
2. 实现灵感重置机制
3. 实现 MIDI 输出（Score → midi_writer → .mid 文件）
4. 验证：输入文字描述 → 自动输出多轨 MIDI 文件

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| Magenta 依赖旧版 Python/TF，未来可能彻底无法运行 | 音乐引擎不可用 | MusicEngineInterface 抽象层 + 至少准备一个备用引擎实现 |
| SelectorGroupChat 的 LLM 选择不准确，导致 Agent 发言顺序混乱 | 管线失控 | 设计详细的 Selector Prompt；设置 max_messages 硬上限；必要时切换为 `selector_func` 自定义选择逻辑 |
| Score JSON 过大导致 LLM 上下文溢出 | 推理质量下降 | 分层上下文策略：摘要模式 / 聚焦模式 / 全量模式 |
| Agent 迭代循环不收敛，质量分数不上升 | 无限循环 | 最多 5 轮精修迭代 + 3 次灵感重置，之后强制输出最佳版本 |
| Magenta 微服务进程崩溃 | 阶段二/灵感重置失败 | 降级为纯 LLM 模式：Composer 直接用 LLM 生成音符序列（质量较低但可用） |
