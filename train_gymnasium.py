#!/usr/bin/python3

import argparse
import logging
from typing import List

import numpy as np

try:
	import gymnasium as gym
	from gymnasium import spaces
except ImportError as exc:
	raise SystemExit("Missing dependency: gymnasium. Install with `pip install gymnasium`.") from exc

try:
	from stable_baselines3 import PPO
	from stable_baselines3.common.callbacks import BaseCallback
	from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecMonitor
except ImportError as exc:
	raise SystemExit("Missing dependency: stable-baselines3. Install with `pip install stable-baselines3`.") from exc

from ios import Game, IOSEnv


def build_command_list() -> List[str]:
	"""Build a fixed discrete command set for RL."""
	game = Game()
	item_codes = [item[0] for item in game.items]
	item_codes_only = [item[0] for item in game.items[:24]]
	target_codes_only = [item[0] for item in game.items[24:43]]

	commands = [
		"N", "S", "E", "W",
		"GO NORTH", "GO SOUTH", "GO EAST", "GO WEST",
		"EAT", "DRINK", "RUB", "WAVE", "HELP", "SCRATCH", "WAIT",
	]

	object_verbs = [
		"GET", "DROP", "OPEN", "EAT", "DRINK", "RUB", "WAVE",
		"TAP", "HIT", "ATTACK", "BREAK", "STRIKE",
		"SCRATCH", "CHIP", "CATCH", "RIDE", "FILL", "GO",
	]
	for verb in object_verbs:
		for code in item_codes:
			commands.append(f"{verb} {code}")

	for item_code in item_codes_only:
		for target_code in target_codes_only:
			commands.append(f"GIVE {item_code} {target_code}")

	# Known multi-word SAY phrases used by the expert solution.
	commands.extend([
		"SAY STONY WORDS",
		"SAY REMEMBER OLD TIMES",
	])

	# Deduplicate while preserving order.
	return list(dict.fromkeys(commands))


class IOSGymEnv(gym.Env):
	"""Gymnasium adapter over IOSEnv."""

	metadata = {"render_modes": ["ansi"]}

	def __init__(self, max_steps: int = 300, seed: int | None = None, log_episodes: bool = True):
		super().__init__()
		self.base_env = IOSEnv(debug=False)
		self.max_steps = max_steps
		self.seed_value = seed
		self.steps = 0
		self.log_episodes = log_episodes
		self.episode_return = 0.0
		self.episode_index = 0

		self.commands = build_command_list()
		self.action_space = spaces.Discrete(len(self.commands))

		# Observation vector:
		# [6 scalar stats] + location one-hot + carried-items bitmask + visible-items bitmask
		self.num_locations = len(Game().locations)
		self.num_items = len(Game().items)
		self.obs_size = 6 + self.num_locations + self.num_items + self.num_items

		self.observation_space = spaces.Box(
			low=-1.0,
			high=1.0,
			shape=(self.obs_size,),
			dtype=np.float32,
		)

	def _encode_obs(self, obs: dict) -> np.ndarray:
		vec = np.zeros(self.obs_size, dtype=np.float32)

		# Normalized scalar features.
		vec[0] = np.clip(obs["time_remaining"] / 1000.0, 0.0, 1.0)
		vec[1] = np.clip(obs["strength"] / 200.0, -1.0, 1.0)
		vec[2] = np.clip(obs["wisdom"] / 200.0, -1.0, 1.0)
		vec[3] = np.clip(obs["food"] / 20.0, 0.0, 1.0)
		vec[4] = np.clip(obs["drink"] / 20.0, 0.0, 1.0)
		vec[5] = np.clip(obs["items_held"] / 43.0, 0.0, 1.0)

		# Location one-hot.
		loc_idx = int(obs["location"]) - 1
		if 0 <= loc_idx < self.num_locations:
			vec[6 + loc_idx] = 1.0

		# Item masks.
		inv_offset = 6 + self.num_locations
		vis_offset = inv_offset + self.num_items

		for item in obs["inventory"]:
			item_idx = int(item["id"]) - 1
			if 0 <= item_idx < self.num_items:
				vec[inv_offset + item_idx] = 1.0

		for item in obs["visible_items"]:
			item_idx = int(item["id"]) - 1
			if 0 <= item_idx < self.num_items:
				vec[vis_offset + item_idx] = 1.0

		return vec

	def reset(self, *, seed=None, options=None):
		if seed is None:
			seed = self.seed_value
		self.steps = 0
		self.episode_return = 0.0
		obs, info = self.base_env.reset(seed=seed)
		return self._encode_obs(obs), info

	def step(self, action):
		self.steps += 1
		command = self.commands[int(action)]
		obs, reward, done, info = self.base_env.step(command)
		self.episode_return += float(reward)
		terminated = bool(done)
		truncated = self.steps >= self.max_steps
		info = dict(info)
		info["command"] = command
		if terminated or truncated:
			self.episode_index += 1
			info["episode_return"] = self.episode_return
			if self.log_episodes:
				logging.info(
					"Episode %d finished | return=%.2f | steps=%d | terminated=%s | truncated=%s | status=%s",
					self.episode_index,
					self.episode_return,
					self.steps,
					terminated,
					truncated,
					info.get("status", ""),
				)
		return self._encode_obs(obs), float(reward), terminated, truncated, info

	def render(self):
		return self.base_env.render()


class TrainLogCallback(BaseCallback):
	def __init__(self, print_every_steps: int = 10_000):
		super().__init__()
		self.print_every_steps = max(1, int(print_every_steps))

	def _on_step(self) -> bool:
		if self.num_timesteps % self.print_every_steps == 0:
			logging.info("Training progress | timesteps=%d", self.num_timesteps)
		return True


def collect_expert_demos(env: "IOSGymEnv", expert_commands: List[str]):
	"""Replay expert commands through env; return (obs, actions) arrays."""
	command_to_idx = {cmd: i for i, cmd in enumerate(env.commands)}

	missing = [c for c in expert_commands if c not in command_to_idx]
	if missing:
		raise ValueError(
			f"Expert commands missing from action space ({len(missing)}): {missing[:10]}"
		)

	obs, _ = env.reset()
	observations, actions = [], []
	total_reward = 0.0

	for i, cmd in enumerate(expert_commands):
		action_idx = command_to_idx[cmd]
		observations.append(obs)
		actions.append(action_idx)
		obs, reward, terminated, truncated, info = env.step(action_idx)
		total_reward += reward
		logging.info(
			"[expert %3d] %-22s reward=%+.2f status=%s",
			i, cmd, reward, info.get("status", "")
		)
		if terminated:
			logging.info("Expert episode TERMINATED at step %d (return=%.2f)", i, total_reward)
			break
		if truncated:
			logging.warning("Expert episode truncated at step %d", i)
			break

	logging.info(
		"Collected %d expert (obs, action) pairs | return=%.2f",
		len(actions), total_reward
	)
	return np.array(observations, dtype=np.float32), np.array(actions, dtype=np.int64)


def behavior_clone(model: PPO, observations: np.ndarray, actions: np.ndarray,
				   epochs: int = 20, batch_size: int = 64, lr: float = 3e-4):
	"""Supervised pre-training of PPO's policy using expert (obs, action) pairs."""
	import torch as th
	from torch.nn import functional as F

	device = model.device
	obs_t = th.as_tensor(observations, dtype=th.float32, device=device)
	act_t = th.as_tensor(actions, dtype=th.long, device=device)
	n = len(obs_t)

	optimizer = th.optim.Adam(model.policy.parameters(), lr=lr)

	logging.info("Behavior cloning | samples=%d | epochs=%d | batch=%d", n, epochs, batch_size)

	for epoch in range(epochs):
		perm = th.randperm(n, device=device)
		losses, correct = [], 0
		for start in range(0, n, batch_size):
			idx = perm[start:start + batch_size]
			dist = model.policy.get_distribution(obs_t[idx])
			logits = dist.distribution.logits
			loss = F.cross_entropy(logits, act_t[idx])

			optimizer.zero_grad()
			loss.backward()
			optimizer.step()

			losses.append(loss.item())
			correct += int((logits.argmax(dim=-1) == act_t[idx]).sum().item())

		logging.info(
			"BC epoch %2d/%d | loss=%.4f | acc=%.1f%%",
			epoch + 1, epochs, sum(losses) / max(1, len(losses)), 100.0 * correct / n
		)


def _make_env_factory(max_steps: int, seed: int, rank: int, log_episodes: bool):
	"""Return a zero-arg callable suitable for SubprocVecEnv/DummyVecEnv."""

	def _init():
		env = IOSGymEnv(
			max_steps=max_steps,
			seed=seed + rank,
			log_episodes=log_episodes,
		)
		return env

	return _init


def build_vec_env(n_envs: int, max_steps: int, seed: int, log_episodes: bool):
	"""Build a vectorised env. SubprocVecEnv if n_envs > 1, else DummyVecEnv."""
	factories = [
		_make_env_factory(max_steps=max_steps, seed=seed, rank=i, log_episodes=log_episodes)
		for i in range(n_envs)
	]
	if n_envs > 1:
		vec = SubprocVecEnv(factories, start_method="spawn")
	else:
		vec = DummyVecEnv(factories)
	return VecMonitor(vec)


def main():
	parser = argparse.ArgumentParser(description="Train PPO agent for Island of Secrets.")
	parser.add_argument("--timesteps", type=int, default=200_000, help="Total PPO timesteps.")
	parser.add_argument("--max-steps", type=int, default=300, help="Max episode length before truncation.")
	parser.add_argument("--seed", type=int, default=42, help="Random seed.")
	parser.add_argument("--save-path", type=str, default="models/ios_ppo", help="Path prefix to save the model.")
	parser.add_argument("--log-every", type=int, default=10_000, help="Log training progress every N timesteps.")
	parser.add_argument("--quiet-episodes", action="store_true", help="Disable per-episode summary logs.")
	parser.add_argument(
		"--n-envs",
		type=int,
		default=8,
		help="Number of parallel environments for SubprocVecEnv (default: 8).",
	)
	parser.add_argument(
		"--net-arch",
		type=int,
		nargs="+",
		default=[256, 256],
		help="Policy/value MLP hidden sizes (e.g. --net-arch 256 256).",
	)
	parser.add_argument(
		"--progress-bar",
		action="store_true",
		help="Show SB3 progress bar (requires `pip install stable-baselines3[extra]`).",
	)
	parser.add_argument(
		"--bc-pretrain",
		action="store_true",
		help="Warm-start policy with behavior cloning on the hard-coded expert solution.",
	)
	parser.add_argument("--bc-epochs", type=int, default=20, help="BC pretraining epochs.")
	parser.add_argument("--bc-batch-size", type=int, default=64, help="BC batch size.")
	parser.add_argument("--bc-lr", type=float, default=3e-4, help="BC learning rate.")
	parser.add_argument(
		"--bc-only",
		action="store_true",
		help="Run BC pretraining only; skip PPO learn().",
	)
	parser.add_argument(
		"--device",
		type=str,
		default="cuda",
		choices=["auto", "cpu", "cuda", "mps"],
		help="Torch device for policy/value networks (default: cuda).",
	)
	parser.add_argument(
		"--allow-cpu-fallback",
		action="store_true",
		help="If --device=cuda but CUDA is unavailable, silently fall back to CPU.",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

	import torch as th

	if args.device == "cuda":
		if not th.cuda.is_available():
			msg = "CUDA requested (--device=cuda) but torch.cuda.is_available() is False."
			if args.allow_cpu_fallback:
				logging.warning("%s Falling back to CPU.", msg)
				args.device = "cpu"
			else:
				raise SystemExit(
					f"{msg}\n"
					"Install CUDA-enabled PyTorch (e.g. "
					"`pip install --index-url https://download.pytorch.org/whl/cu128 torch`) "
					"or pass --allow-cpu-fallback."
				)
		else:
			logging.info("CUDA device: %s", th.cuda.get_device_name(0))

	n_envs = max(1, int(args.n_envs))
	logging.info("Building %d parallel envs...", n_envs)
	env = build_vec_env(
		n_envs=n_envs,
		max_steps=args.max_steps,
		seed=args.seed,
		log_episodes=(not args.quiet_episodes) and n_envs == 1,
	)

	# With n_envs parallel rollouts, scale n_steps per env so PPO still sees
	# a decently sized buffer per update.
	n_steps_per_env = max(128, 2048 // n_envs)
	rollout_size = n_steps_per_env * n_envs
	batch_size = min(512, rollout_size)
	if rollout_size % batch_size != 0:
		# Ensure batch_size divides rollout_size.
		batch_size = rollout_size // max(1, (rollout_size // batch_size))

	policy_kwargs = dict(net_arch=list(args.net_arch))
	logging.info(
		"PPO config | n_envs=%d | n_steps=%d | rollout=%d | batch=%d | net_arch=%s",
		n_envs, n_steps_per_env, rollout_size, batch_size, args.net_arch,
	)

	model = PPO(
		"MlpPolicy",
		env,
		verbose=1,
		seed=args.seed,
		n_steps=n_steps_per_env,
		batch_size=batch_size,
		gamma=0.99,
		learning_rate=3e-4,
		device=args.device,
		policy_kwargs=policy_kwargs,
	)
	logging.info("Training on device: %s", model.device)

	if args.bc_pretrain or args.bc_only:
		from expert_solution import EXPERT_COMMANDS
		demo_env = IOSGymEnv(
			max_steps=max(args.max_steps, len(EXPERT_COMMANDS) + 10),
			seed=args.seed,
			log_episodes=False,
		)
		obs_arr, act_arr = collect_expert_demos(demo_env, EXPERT_COMMANDS)
		behavior_clone(
			model, obs_arr, act_arr,
			epochs=args.bc_epochs,
			batch_size=args.bc_batch_size,
			lr=args.bc_lr,
		)
		if args.bc_only:
			model.save(args.save_path)
			logging.info("BC-only run finished. Model saved to %s.zip", args.save_path)
			env.close()
			return

	callback = TrainLogCallback(print_every_steps=args.log_every)

	progress_bar = args.progress_bar
	if progress_bar:
		try:
			import tqdm  # noqa: F401
			import rich  # noqa: F401
		except ImportError:
			logging.warning(
				"tqdm/rich not available; disabling progress bar. "
				"Install with `pip install stable-baselines3[extra]`."
			)
			progress_bar = False

	model.learn(total_timesteps=args.timesteps, progress_bar=progress_bar, callback=callback)
	model.save(args.save_path)
	env.close()
	print(f"Model saved to {args.save_path}.zip")


if __name__ == "__main__":
	main()
