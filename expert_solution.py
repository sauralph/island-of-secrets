"""Hard-coded expert solution for Island of Secrets.

Derived from solution.md. Commands use the canonical
"VERB <3-letter-item-code>" format so they map 1-to-1 to the discrete
action space built by train_gymnasium.build_command_list().

Note: the game has random events (teleports, mazes, canyonbeast spawn
location, well-of-despair exits). This script is a best-effort linear
trace that assumes "lucky" RNG. It is intended as warm-start data for
imitation learning; not every playthrough will succeed end-to-end.
"""

EXPERT_COMMANDS = [
	# --- Phase 1: Mainland gathering ---
	"S", "E", "E", "S",
	"GET APP",
	"GIVE APP SNA",
	"W",
	"GET LOA", "GET BOT",
	"OPEN CHE",
	"GET RAG", "GET HAM",
	"E", "S", "E", "S", "E",
	"GET FLI",
	"W", "N", "W", "N", "N", "W", "W", "W", "W", "S",
	"GET JUG", "FILL JUG",
	"N", "E", "E", "N", "W", "N", "W", "S",
	"GET MUS", "GET PAR",
	"N", "E", "E", "E", "E",
	"RUB STO", "RUB STO", "GET PEB",
	"W", "S", "W", "S", "E", "E", "S", "S", "W", "W",
	"GET AXE",
	"S", "S", "W", "W",
	"SCRATCH SAG", "GET FLO",
	"E", "E", "E", "E",
	"GIVE WAT VIL",
	"GET STA",
	"E", "E",

	# --- Phase 2: Secondary items ---
	"BREAK ROO", "GET SAP",
	"GIVE JUG SWA",
	"E", "E", "E",
	"GET COA",
	"W", "W", "N", "N",
	"CHIP COL", "GET CHI",
	"E", "E",
	"GET BIS",
	"S", "W", "W", "S", "W", "W", "W", "W", "W", "N", "N", "W", "S",
	"GET ROP",
	"N", "N",
	"GET MEL", "GET WIN",
	"E", "N", "N", "E", "N", "N",

	# --- Phase 3: Canyonbeast hunt (oscillate E/W until spotted) ---
	"E", "W", "E", "W", "E", "W",
	"CATCH CAN",

	# --- Phase 4: Egg + return to boat ---
	"S", "S", "E",
	"RIDE CAN",
	"E", "S", "S",
	"GET EGG",
	"N", "N", "W", "W", "W", "S",
	"GO BOA",

	# --- Phase 5: On the Island of Secrets ---
	"N",
	"SAY STONY WORDS",
	"N", "N",
	"GET TOR",
	"E",
	"WAVE TOR",
	"S",
	"GIVE CHI SCA", "GIVE FLO SCA",
	"SAY REMEMBER OLD TIMES",
	"E",

	# --- Phase 6: Well-of-despair + endgame (assumes lucky maze exits) ---
	"N", "N", "N", "N",
	"E",
	"DROP EGG", "DROP COA",
	"GET CLO",
	"GIVE PEB MED",
	"STRIKE FLI",
	"BREAK STA",
]

# Context-triggered interjection when the swampman blocks the path.
SWAMPMAN_INTERJECTION = "GIVE JUG SWA"
