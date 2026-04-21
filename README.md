# Island of Secrets

Back in the 80s, when I was first learning to program on my dad's ZX Spectrum, there was a really good collection of books on computing published by Usborne. Two of these, Mystery of Silver Mountain and Island of Secrets, were full text adventure games that you could type in yourself, and use the descriptions and pictures in the book to help you without requiring any graphics. The program code was messy by today's standards (as it was all in BASIC), there was no code documentation and parts of them were intentionally obfuscated in order to make sure typing the program in didn't spoil the game. You can download PDF versions of both of these books for free from https://usborne.com/gb/books/computer-and-coding-books 

These days I mostly use emulators to play Spectrum games, and I have both books' games as TAP files. However, the limitations of the emulation hinder the gameplay, so I always wanted to port them to a modern PC. Indeed, the Usborne website explicitly grants permission to do this. I spent a while digging around to see if anyone has done it already, but due to my impatience and the fact that I think it would be a fun programming challenge, I decided to do it myself. There is already a port of Mystery of Silver Mountain made using [Quest](https://textadventures.co.uk/quest) so I've started with Island of Secrets, and I'm converting it to Python, which I guess is to modern youngsters what BASIC was to me.

Perhaps once I'm done, I might try improving it by adding pictures from the book to the game itself.

No working code here yet... the original source code in lovely ZX BASIC is [ios.bas](https://raw.githubusercontent.com/ads04r/island-of-secrets/refs/heads/master/ios.bas) and my code documentation so far is [notes.md](https://github.com/ads04r/island-of-secrets/blob/master/notes.md).

## Reinforcement Learning Training

The Python port of the game is wrapped in a Gymnasium-compatible environment so a
reinforcement-learning agent can be trained to solve it. The stack is:

- `ios.py` — game engine + `IOSEnv` programmatic wrapper (observations, rewards,
  termination).
- `train_gymnasium.py` — Gymnasium adapter (`IOSGymEnv`), PPO training via
  Stable-Baselines3, parallel rollouts via `SubprocVecEnv`, and optional
  behavior-cloning warm-start from the hard-coded solution.
- `expert_solution.py` — canonical command sequence that solves the game,
  used for behavior cloning.
- `evaluate.py` — loads a saved model and reports win-rate, episode length,
  items collected, locations visited, etc.

### Environment setup

**Python 3.12 is required** on Windows if you want GPU training. The RTX
50-series (Blackwell, `sm_120`) is only supported by PyTorch's `cu128`
wheels, and at the time of writing those wheels only load cleanly under
Python 3.12 on machines with Windows Application Control policies.

```powershell
py -3.12 -m venv venv312
.\venv312\Scripts\Activate.ps1
python -m pip install --index-url https://download.pytorch.org/whl/cu128 torch
python -m pip install numpy gymnasium stable-baselines3 tqdm rich
```

Verify CUDA:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

If you only need CPU training, a plain `pip install torch numpy gymnasium stable-baselines3`
inside any venv is enough. Pass `--device cpu` (or `--allow-cpu-fallback`) to the trainer.

### Recommended training command

Default run (best balance, ~10–20 min on a mid-range RTX GPU):

```powershell
python train_gymnasium.py `
  --timesteps 500000 `
  --n-envs 8 `
  --max-steps 300 `
  --device cuda `
  --bc-pretrain --bc-epochs 30 `
  --net-arch 256 256 `
  --quiet-episodes `
  --progress-bar `
  --save-path models/ios_ppo_gpu
```

Quick smoke test (~1 min) — use while iterating on code:

```powershell
python train_gymnasium.py --timesteps 20000 --n-envs 8 --device cuda `
  --bc-pretrain --bc-epochs 10 --quiet-episodes --save-path models/smoke
```

Long overnight run (larger net, more envs, 1–3 h):

```powershell
python train_gymnasium.py `
  --timesteps 3000000 `
  --n-envs 16 `
  --max-steps 300 `
  --device cuda `
  --bc-pretrain --bc-epochs 40 `
  --net-arch 512 512 `
  --quiet-episodes `
  --progress-bar `
  --save-path models/ios_ppo_long
```

### Key CLI flags

| Flag | Default | Purpose |
|---|---|---|
| `--timesteps` | `200000` | Total PPO environment steps. |
| `--n-envs` | `8` | Parallel envs (`SubprocVecEnv`). |
| `--max-steps` | `300` | Episode truncation length. |
| `--device` | `cuda` | `cuda`, `cpu`, `mps`, or `auto`. |
| `--allow-cpu-fallback` | off | Fall back to CPU if CUDA is unavailable. |
| `--net-arch` | `256 256` | MLP hidden sizes for policy & value nets. |
| `--bc-pretrain` | off | Warm-start policy by cloning the expert solution. |
| `--bc-epochs` | `20` | Epochs of supervised BC before PPO starts. |
| `--bc-only` | off | Skip PPO; save the BC-pretrained policy only. |
| `--quiet-episodes` | off | Hide per-episode summary logs. |
| `--progress-bar` | off | SB3 rich progress bar. |
| `--save-path` | `models/ios_ppo` | Where to save the `.zip` checkpoint. |

### Evaluation

Run many episodes and print aggregate stats (win-rate, mean return,
termination breakdown, top actions):

```powershell
python evaluate.py --model models/ios_ppo_gpu.zip --episodes 50
```

Watch a single episode play out step by step:

```powershell
python evaluate.py --model models/ios_ppo_gpu.zip --replay
```

### Expert baseline

Before comparing a trained model, measure the scripted expert — it replays
`expert_solution.EXPERT_COMMANDS` through the same env and reports the same
metrics, giving you an apples-to-apples ceiling/floor to compare against:

```powershell
python evaluate.py --expert --episodes 20
python evaluate.py --expert --replay    # verbose step-by-step run
```

Note: the expert plan assumes lucky RNG (random teleports, maze exits,
canyonbeast spawns). It rarely completes end-to-end, so expect a non-zero
return and partial exploration rather than a 100% win-rate.

### Performance notes

- Env stepping (the text game) is CPU-bound, so most of the speedup from
  `--n-envs > 1` comes from parallel game workers, not the GPU.
- The GPU still helps once `--net-arch` is larger than the SB3 default
  (`[64, 64]`); with `[256, 256]` or `[512, 512]` forward/backward passes
  become a meaningful fraction of wall-clock time.
- If PPO throughput plateaus, first bump `--n-envs`, then `--net-arch`.
- Without `--bc-pretrain` the agent rarely finds the full solution within
  reasonable budgets — the expert warm-start is the single biggest lever.
