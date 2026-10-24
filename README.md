# LYLA-AI

LYLA runs Qwen3-14B locally through `llama-cpp-python`. The model file is
downloaded from Hugging Face on first use and cached on this computer at
`%USERPROFILE%\.cache\huggingface\hub`. After the model is cached, text
generation runs locally; LYLA does not send conversation prompts to a hosted
inference service.
An explicitly approved FRIDAY weather lookup is the exception for external
data: it sends only the place name entered for that lookup to Open-Meteo.

LYLA's response handling hides Qwen `<think>` reasoning blocks and displays
only the final user-facing answer. Conversation context is kept in memory
while LYLA is running; only Soul notes and personality that you explicitly
save persist locally.

## Install

From the project directory, install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run

Install LYLA as a command from the project directory (repeat this after
updating the project):

```powershell
python -m pip install -e .
```

After installation, type this in PowerShell to launch the dashboard:

```powershell
lyla
```

LYLA opens the dashboard in your browser and runs its local backend in the
terminal window. Keep that terminal open while using the app; press Ctrl+C
there to close it. The backend only listens on `127.0.0.1`. If the `lyla`
command is not recognized immediately after installation, close and reopen
PowerShell so it refreshes its PATH.

You can also launch from the project directory without installing the command:

```powershell
python -m src.web_app
```

The terminal interface and the earlier native window are also available:

```powershell
lyla-cli
python -m src.desktop_app
```

This command can be started without importing or downloading the language
model. The model loads on the first ordinary AI request. If model startup
fails, LYLA reports that the local model could not be loaded and keeps the
command loop available for built-in responses and memory controls; if speech
fails, LYLA reports the voice problem and still prints responses.

## Dashboard chat and Voicebox

The LYLA dashboard is based on `src/web/dashboard.html`, the dashboard design
provided for the project. It lets you chat by typing. Text is always shown,
and speech is optional: select **Speak latest reply** when you want LYLA to
say a reply. Use **Open Voicebox** to open the Voicebox app and configure or
fine-tune your voice there. Voicebox is a separate application; LYLA connects
to its local API at `http://127.0.0.1:17493`. Open Voicebox before using
speech.

In **Voice settings**, you can enter a Voicebox profile name or ID and, if
needed, browse to the Voicebox shortcut or executable. Leave the profile blank
to use Voicebox's configured default. The connection test checks that
Voicebox's local `/speak` endpoint is available. LYLA only permits HTTP
loopback URLs for the Voicebox bridge so speech text is not sent to a remote
host.

The dashboard also includes a local clock, session focus controls, a
conversation log, a text chat panel, quick spoken lines, and hide/show module
buttons. Agents, Today, System, Log, and Text are shown by default. Agent
routing is automatic: everyday conversation stays with LYLA, while clear
coding, forecast/analysis, defensive security, and risk-review requests are
directed to JARVIS, FRIDAY, EDITH, and ULTRON respectively. The dashboard
highlights which role handled the latest request. Ambiguous requests stay with
LYLA, whose instructions ask for clarification rather than guessing. LYLA,
JARVIS, FRIDAY, EDITH, and ULTRON are role modes that share the same local
Qwen model; they are not separate models or autonomous processes. JARVIS gives
coding guidance and has a user-controlled workspace panel described below.
FRIDAY has no general web access; the separate weather panel described below
provides a user-approved Open-Meteo forecast. EDITH can check one selected
project file locally but cannot scan the computer or other systems. ULTRON
offers read-only critical review. Focus and recent chat stay in memory only
for the current run. The decorative activity meters are UI indicators, not
hardware or model performance readings.

Each role now has a distinct response style as well as a task focus: LYLA is
warm and lightly teasing; JARVIS is formal and technically precise; FRIDAY is
brisk and explicit about evidence and uncertainty; EDITH uses a neutral,
film-faithful system voice; and ULTRON is a skeptical, read-only reviewer.
These are newly written, high-level personality adaptations, not copied
dialogue. Personality does not grant tools, access, authority, or human
feelings. EDITH's alternate, playful VisionQuest interpretation is not enabled.
The role-specific instructions guide a shared model; they do not create
independent agents or give the model direct access to the workspace tools.

### FRIDAY weather panel

The dashboard's **FRIDAY Weather** panel fetches current conditions and a
seven-day forecast from Open-Meteo. Each lookup requires checking a consent box;
only the entered place name is sent to Open-Meteo's geocoder, and no chat text
or saved memory is sent. Ambiguous place names are reported for the user to
clarify rather than guessed. Results show the retrieval time, local forecast
timezone, units, source documentation, and a note that model guidance is not a
guarantee or an official warning. An internet connection is required. In-chat
FRIDAY does not have general browsing or automatic access to these results.

### EDITH defensive file review

The **EDITH Review** panel runs local, read-only pattern checks against one
UTF-8 file you select from the project. It checks for potential hard-coded
credential patterns and a short list of Python risk patterns; detected
credential values are redacted. The file is not executed, modified, sent to
the model, or sent over the network. This is not a full security audit:
heuristics can miss issues or flag safe code, and an empty report is not proof
that the file is safe.

### ULTRON review panel

The **ULTRON Review** panel accepts a plan or draft of up to 10,000
characters and asks the local Qwen model for a read-only critique: a verdict,
ranked failure modes, assumptions or missing evidence, and practical
mitigations. Only text submitted for that standalone request is provided;
chat history and saved memory are not included. ULTRON does not inspect files,
execute code, verify external facts, or modify the text. Treat its analysis as
advice to check against evidence, not as a guarantee.

### JARVIS workspace panel

The dashboard's **JARVIS Workspace** panel can load one UTF-8 file no larger
than 1 MB from the project directory, show its exact diff, and apply that
specific change after the user reviews and checks the approval box. Approval is
one-use, expires after five minutes, and is rejected if the file changed since
the preview. Line endings are normalized in the editor and the existing file's
line-ending style is retained when applying an edit. Paths must stay inside the
project; symlinks, binary files, and files larger than 1 MB are rejected. LYLA
can send a selected file of up to 10,000 characters to JARVIS for review;
JARVIS treats the file as untrusted data and can suggest a replacement. The
user pastes that replacement into the editor and approves the exact diff. LYLA
does not expose arbitrary shell commands or let the model apply edits from
chat.

Running tests requires a separate explicit confirmation and always runs the
fixed command `python -m unittest discover -s tests` using LYLA's current
Python interpreter, with a 120-second timeout. This executes project test code
with the current Windows account's permissions; only run tests in a workspace
you trust. The panel shows the captured output. File edits and test runs are
local and user-triggered.

### Automatic-routing benchmark

The rule-based router has a small, labeled regression set of 30 requests in
`tests/test_agents.py`. It covers everyday LYLA conversations, each specialist,
and unclear requests that should not be handed off. The same test file checks
that each role retains its distinct personality and its stated capability
boundaries. The initial baseline routes
30/30 correctly (100%) on this set, including 12 LYLA cases. The test requires
at least 27/30 (90%); this is a target for these fixed examples, not a claim of
general routing accuracy. Run it with:

```powershell
python -m unittest discover -s tests -p "test_agents.py"
```

Add a labeled example whenever routing behavior changes, and keep ambiguous or
ordinary requests in the set to catch unnecessary specialist handoffs.

### Session chat-task trace

Each valid dashboard chat request receives a task ID and a session-only record
with its message, selected agent, routing source, start time, completion time,
status (`in_progress`, `completed`, or `failed`), and failure detail when
available. The dashboard shows the latest task ID and outcome. The local
`GET /api/tasks` endpoint returns the most recent records; the in-memory
history is capped at 100 and is cleared when LYLA closes. It is a trace of chat
requests, not a persistent task queue, an audit log, or proof that planned
specialist tools ran.

Install Voicebox separately from the
[official Windows releases](https://github.com/jamiepine/voicebox/releases/latest).
Its first speech generation may download the selected TTS model.

The first conversation that needs the language model downloads
`Qwen_Qwen3-14B-Q5_K_M.gguf` (about 10.5 GB). The configured runtime uses the
chat template embedded in the Qwen GGUF, CPU only, up to 12 CPU threads, an
8,192-token context, and a 384-token response limit to reduce resource use and
avoid unnecessarily long generations. The context setting limits how much
history the model can consider. Model weights, the context cache, and other
Python/runtime overhead all use memory; speed still depends on the computer's
CPU and memory bandwidth.

LYLA's local `get_time` tool reports the computer's current local date and
time.

## LYLA's memory

- **Mind** is short-term conversation context and focus. It stays in memory
  only for the current run. Use `/mind`, `/focus <topic>`, `/focus`, or
  `/clear-mind` to inspect, set, clear, or reset it.
- **Soul** is LYLA's saved personality and notes. LYLA does not automatically
  save personal details. Use `/remember <note>` to opt in, `/soul` to inspect
  saved information, `/forget <number>` to remove one note, `/persona
  <instructions>` to customize personality, and `/clear-soul` to reset all
  saved notes and personality.
- Soul data is plain JSON on this computer at `%USERPROFILE%\.lyla-ai\soul.json`.
  Set `LYLA_DATA_DIR` to choose another local folder.

## Conversation evaluation

After installing and downloading the model on first use, run:

```powershell
python -m src.evaluate_conversations
```

The small evaluation set checks expected answer terms, simple instruction
constraints, and whether the response repeats the full prompt. It also asks
you to rate whether LYLA stayed in character; that judgment is subjective.
These checks are useful for comparing changes, but are not a broad AI quality
benchmark.
