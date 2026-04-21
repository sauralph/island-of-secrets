#!/usr/bin/python3
"""Evaluate a trained Island of Secrets PPO model.

Usage:
	python evaluate.py --model models/ios_ppo --episodes 50
	python evaluate.py --model models/ios_ppo --replay  # verbose single episode
"""

import argparse
import logging
import statistics
from collections import Counter

import numpy as np

try:
	from stable_baselines3 import PPO
except ImportError as exc:
	raise SystemExit("Missing dependency: stable-baselines3.") from exc

from train_gymnasium import IOSGymEnv


def run_episode(model, env, deterministic=True, render=False):
	obs, info = env.reset()
	done = False
	truncated = False
	total_reward = 0.0
	steps = 0
	commands_used = []
	visited_locations = set()
	final_info = info

	while not (done or truncated):
		action, _ = model.predict(obs, deterministic=deterministic)
		action = int(action)
		command = env.commands[action]
		obs, reward, done, truncated, info = env.step(action)

		total_reward += reward
		steps += 1
		commands_used.append(command)
		visited_locations.add(env.base_env.game.location)
		final_info = info

		if render:
			print(f"[step {steps:3d}] action={command:<22s} reward={reward:+.2f} "
				  f"loc={env.base_env.game.location} status={info.get('status','')}")

	result = {
		"return": total_reward,
		"steps": steps,
		"terminated": bool(done),
		"truncated": bool(truncated),
		"final_status": final_info.get("status", ""),
		"final_strength": env.base_env.game.strength,
		"final_wisdom": env.base_env.game.wisdom,
		"final_time": env.base_env.game.time_remaining,
		"final_location": env.base_env.game.location,
		"items_held": env.base_env.game.items_held,
		"visited_locations": len(visited_locations),
		"won": final_info.get("status") == "YOUR QUEST IS OVER",
		"commands": commands_used,
	}
	return result


def summarize(results):
	n = len(results)
	wins = sum(1 for r in results if r["won"])
	returns = [r["return"] for r in results]
	steps = [r["steps"] for r in results]
	items = [r["items_held"] for r in results]
	locs = [r["visited_locations"] for r in results]

	def stats(xs):
		return f"mean={statistics.mean(xs):.2f} median={statistics.median(xs):.2f} min={min(xs):.2f} max={max(xs):.2f}"

	print()
	print("=" * 60)
	print(f"EVALUATION SUMMARY ({n} episodes)")
	print("=" * 60)
	print(f"Win rate:            {wins}/{n} ({100.0 * wins / n:.1f}%)")
	print(f"Return:              {stats(returns)}")
	print(f"Steps:               {stats(steps)}")
	print(f"Items held (final):  {stats(items)}")
	print(f"Unique locations:    {stats(locs)}")

	termination_reasons = Counter(r["final_status"] or "(empty)" for r in results)
	print()
	print("Termination reasons:")
	for reason, count in termination_reasons.most_common():
		print(f"  {count:3d}x  {reason}")

	all_commands = [cmd for r in results for cmd in r["commands"]]
	top = Counter(all_commands).most_common(10)
	print()
	print("Top 10 actions used:")
	for cmd, count in top:
		print(f"  {count:5d}  {cmd}")
	print("=" * 60)


def main():
	parser = argparse.ArgumentParser(description="Evaluate a trained Island of Secrets PPO model.")
	parser.add_argument("--model", type=str, required=True, help="Path to saved model (no .zip).")
	parser.add_argument("--episodes", type=int, default=20, help="Number of episodes to run.")
	parser.add_argument("--max-steps", type=int, default=500, help="Max steps per episode.")
	parser.add_argument("--seed", type=int, default=0, help="Base random seed (incremented per episode).")
	parser.add_argument(
		"--stochastic",
		action="store_true",
		help="Sample actions instead of using deterministic argmax.",
	)
	parser.add_argument(
		"--replay",
		action="store_true",
		help="Run one verbose episode printing every step, then exit.",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

	logging.info("Loading model from %s.zip", args.model)
	env = IOSGymEnv(max_steps=args.max_steps, seed=args.seed, log_episodes=False)
	model = PPO.load(args.model, env=env)

	if args.replay:
		print(f"\n== REPLAY (deterministic={not args.stochastic}) ==\n")
		result = run_episode(model, env, deterministic=not args.stochastic, render=True)
		print(f"\nFinished: return={result['return']:.2f} steps={result['steps']} "
			  f"won={result['won']} status={result['final_status']}")
		return

	results = []
	for ep in range(args.episodes):
		env.seed_value = args.seed + ep  # vary seed per episode
		result = run_episode(model, env, deterministic=not args.stochastic, render=False)
		logging.info(
			"Episode %3d | return=%+7.2f | steps=%3d | won=%s | status=%s",
			ep + 1, result["return"], result["steps"], result["won"], result["final_status"],
		)
		results.append(result)

	summarize(results)


if __name__ == "__main__":
	main()
