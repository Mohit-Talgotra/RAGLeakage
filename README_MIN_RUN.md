# Running the reduced Enron grid on a Windows laptop

The reduced grid (`configs/min/`) runs Llama-3.1-8B through Ollama on one laptop GPU (tested target:
RTX 3050 laptop GPU, 6 GB VRAM) plus CPU-only stub runs. It is meant to finish in about a day; the
pilot step tells you how long it will really take on your machine. Nothing here needs a cloud GPU.

## 1. Install

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (PowerShell):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. Install Python 3.14 and the dependencies, from the repository root:
   ```powershell
   uv python install 3.14
   uv sync --python 3.14
   ```
3. Install [Ollama for Windows](https://ollama.com/download), then pull the model (the default build
   is 4-bit, about 4.9 GB):
   ```powershell
   ollama pull llama3.1:8b
   ```
4. Give the model a 4096-token context window so long prompts are not cut silently (older Ollama
   versions default to 2048). Set it once, then restart Ollama from the tray icon:
   ```powershell
   setx OLLAMA_CONTEXT_LENGTH 4096
   ```
   While a run is going, `ollama ps` should show the model at `100% GPU`. If it shows a CPU share,
   close other GPU programs.

## 2. Data

`data/enron_c/` (Enron with canaries, about 2 MB: `corpus.jsonl` and `iam.json`) is committed, so the
clone already has it; nothing to copy. The first run encodes the corpus (cached in `.cache\embeddings\`)
and downloads the MiniLM encoder and cross-encoder from Hugging Face, so it needs internet once.

## 3. Run

All commands from the repository root. `uv run` uses the project's environment; the script also
works when started with `.venv\Scripts\python.exe` directly.

1. **Pilot** (2 seeds x 1 event, a few minutes). It prints the mean seconds per model call and an
   estimate for the full model run:
   ```powershell
   uv run python scripts/run_min_grid.py pilot
   ```
   To time it again later, delete `results\p_min_pilot\` and `.cache\llm\` first (cached calls are
   not timed).
2. **Paraphrase bank** (once, about 2 hours on the GPU): model-written rewordings of every Enron
   question, which the model run uses for its fresh-session probes.
   ```powershell
   uv run python scripts/run_min_grid.py paraphrases
   ```
   It must end with `0 questions still missing`. It retries missing questions itself with new
   instruction variants (up to five rounds). If some are still missing after that, stop and report
   the questions it lists: running it again repeats the same cached attempts. The model run refuses
   to start while any question is missing, since it would otherwise stop with a KeyError partway
   through.
3. **Model run** (the long one):
   ```powershell
   uv run python scripts/run_min_grid.py model
   ```
4. **Stub runs** (CPU only, no bank needed). They can run in a second terminal at any time, including
   while the paraphrase bank or the model run is going:
   ```powershell
   uv run python scripts/run_min_grid.py stub
   ```

Both print one line when each cell starts and ends, skip cells that already finished, and can be
restarted after an interruption (sleep, reboot). Keep the laptop plugged in and stop it from
sleeping during the model run.

## 4. Results

Each run writes `results\<name>\runs\` (raw logs) and `results\<name>\analysis\` (tables and
figures). `research_paper/RESULTS_TODO.md` says which column fills which slot of the paper. Copy the
`results\p_min_*` folders back to the machine where the paper is edited, together with
`data\paraphrases.json` (the rewordings the model run used; commit it with the results).
