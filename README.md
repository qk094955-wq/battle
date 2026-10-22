# battle# 🎯 MINI BATTLE ROYALE

A beginner-friendly, turn-based **battle royale survival game** built with **Python and Streamlit**.
Loot weapons, fight enemy bots, manage your health and ammunition, and stay inside the shrinking safe zone to become the **last survivor**.

The whole game lives in a single `app.py` file, so it is easy to read, run, upload to GitHub and deploy on Streamlit Community Cloud.

---

## Game Objective

- Eliminate **every enemy bot** while staying alive.
- Stay inside the **safe zone** – the storm outside it hurts everyone.
- You **win** when all bots are eliminated and you are still alive.
- You **lose** when your health reaches zero.

## Main Features

- Dark, military-style gaming interface with a live SVG battlefield
- 8–14 enemy bots with a simple AI state machine: **roaming, chasing, attacking, escaping the zone**
- 4 weapons (Pistol, Assault Rifle, Shotgun, Sniper Rifle), each with its own damage, range, magazine, reserve ammo and firing cooldown
- Trees, rocks and walls that act as **cover** (they block movement and bullets)
- Loot: weapons, ammo boxes and health packs (bots sometimes drop supplies)
- 6-phase **shrinking safe zone** with a countdown and damage outside the zone
- Scoring, kill counter, damage tracking, survival time
- Start, Pause, Restart and Play Again – no browser refresh needed
- Victory screen and game-over screen with a full results breakdown

## Technologies Used

- **Python 3.9+**
- **Streamlit** (the only third-party library)
- Python standard library (`math`, `random`, `time`, `html`)
- Inline **SVG** for the arena (no external images or assets)

## Project Structure

Exactly three files:

```
mini-battle-royale/
├── app.py            # the whole game: logic, AI, rendering and interface
├── requirements.txt  # Python dependencies
└── README.md         # this documentation
```

## Installation

1. Install Python 3.9 or newer from <https://www.python.org/downloads/>.
2. Put the three files in one folder and open a terminal in that folder.
3. (Recommended) create a virtual environment:

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

4. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## How to Launch the Game Locally

```bash
streamlit run app.py
```

Your browser opens automatically (usually at <http://localhost:8501>). Click **START GAME** to begin.

## Controls and Gameplay

The game is **turn-based**: every action you take is one *turn*, which equals **one second** of match time. After each turn the bots move/attack and the safe-zone clock advances. This keeps the game reliable with Streamlit's rerun model.

> Streamlit does not support real-time keyboard input without extra browser code, so all controls are clear on-screen buttons.

| Control | What it does |
|---|---|
| **▲ ◀ ▶ ▼** | Move one tile (blocked by cover, edges and enemies). Walk over loot to pick it up. |
| **⏳ HOLD** | Skip a turn (useful to wait out a weapon cooldown). |
| **Aim at** | Choose a specific bot, or leave on *Auto* to target the nearest enemy in range. |
| **🔫 SHOOT** | Fire the selected weapon at the aimed target. |
| **🔄 RELOAD** | Refill the magazine from reserve ammo (takes a turn). |
| **Weapon list** | Switch weapon (free action, no turn used). |
| **START / PAUSE / RESTART** | Start the match, pause/resume it, or begin a fresh match instantly. |
| **Enemy bots slider** | Choose 8–14 bots for the next match. |

**Invalid actions are safe:** shooting with an empty magazine, an out-of-range target, a blocked line of fire, or walking into a wall just shows a message and does **not** cost a turn or ammo.

**Reading the arena**

- Blue circle = you; numbered circles = bots (colour shows their AI state)
- Red line = current safe-zone edge; yellow dashed line = where the zone will shrink next
- Red-tinted area = storm (damage zone)
- White cross = health pack, gold box = ammo box, coloured tag (PI / AR / SG / SR) = weapon
- Faint dotted ring around you = range of your current weapon
- Yellow dashed reticle = your current target; yellow line = your shot, red line = enemy shot

## Weapons

| Weapon | Damage | Range (tiles) | Magazine | Starting reserve | Cooldown | Notes |
|---|---|---|---|---|---|---|
| **Pistol** | 20 | 9 | 10 | 20 | 1 turn | Start weapon; balanced. |
| **Assault Rifle** | 26 | 13 | 30 | 30 | 1 turn | Best all-rounder. |
| **Shotgun** | 70 | 6 | 6 | 12 | 2 turns | Devastating up close, damage drops with distance. |
| **Sniper Rifle** | 80 | 28 | 5 | 10 | 3 turns | Huge range, slow fire. |

- You start with the **Pistol**, 100 HP, a full magazine and 20 reserve rounds.
- Other weapons are found as loot. Picking up a weapon you already own gives extra ammo.
- Ammo boxes add reserve ammo to **all** weapons you own.
- Accuracy falls with distance, so closer shots hit more often.
- Cooldown = the number of turns between shots. Weapons have independent cooldowns.

## Enemy Bots

Each bot has its own health, speed, detection range, attack range, damage and attack cooldown. AI states:

- **Roaming** – wanders inside the safe zone.
- **Chasing** – moves toward you when you are within its detection range (or after you hit it).
- **Attacking** – shoots when you are in range with a clear line of sight.
- **Escaping** – runs for the safe zone when outside it (or when a shrink is about to happen).

Eliminated bots stop moving and attacking. Bots also take storm damage, so some may die to the zone.

## Safe-Zone Rules

- The arena is a 30 x 30 grid. The zone starts with radius **20** (covers almost everything).
- It shrinks over **6 phases**: radius 20 → 16 → 12 → 9 → 6 → **3.5** (final area, never smaller).
- Phase timers: 16, 14, 12, 10 and 10 turns. The countdown is shown in the **SAFE ZONE** panel.
- Anyone outside the zone takes storm damage each turn: 3, 4, 5, 6, 8, 10 per turn by phase.
- In the final phase the storm slowly grows stronger so the match always ends.

## Scoring Rules

| Event | Points |
|---|---|
| Eliminate an enemy bot (your kill) | **+100** |
| Survive a safe-zone phase | **+50** |
| Collect a health pack | **+10** |
| Win the match | **+500** |

Health packs restore 25 HP (up to 100). If your health is full, the pack stays on the ground. The results screen shows kills, damage dealt and taken, accuracy, survival time, zone phases survived and a score breakdown.

## Troubleshooting

- **`streamlit: command not found`** – activate your virtual environment, or run `python -m streamlit run app.py`.
- **`ModuleNotFoundError: No module named 'streamlit'`** – run `pip install -r requirements.txt` in the same environment you launch from.
- **Page does not open** – open <http://localhost:8501> manually, or check that the port is free (`streamlit run app.py --server.port 8502`).
- **Buttons look disabled** – controls only work while the match is running; press **START GAME** (or **RESUME** if paused).
- **Light text/backgrounds look odd** – open the Streamlit menu (top right) → Settings → choose the *Dark* theme.
- **Game seems stuck after changing code** – press **R** in the browser to rerun, or restart the Streamlit server.
- **Slider changes do nothing mid-match** – the bot count applies to the *next* match (press Restart).

## Upload to GitHub

1. Create a free account at <https://github.com> and click **New repository** (for example `mini-battle-royale`, public).
2. **Easiest way (no Git needed):** on the new repository page choose **Add file → Upload files**, drag in `app.py`, `requirements.txt` and `README.md`, then click **Commit changes**.
3. **Or with Git:**

   ```bash
   git init
   git add app.py requirements.txt README.md
   git commit -m "Add Mini Battle Royale game"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/mini-battle-royale.git
   git push -u origin main
   ```

Make sure the three files are in the **root** of the repository.

## Deploy on Streamlit Community Cloud

1. Push the three files to a GitHub repository (see above).
2. Go to <https://share.streamlit.io> and sign in with your GitHub account.
3. Click **Create app** (or **New app**) and choose **Deploy a public app from GitHub**.
4. Select your repository and branch (`main`).
5. Set **Main file path** to **`app.py`**.
6. Click **Deploy**. Streamlit installs everything from `requirements.txt` and gives you a public link to share.

To run it locally at any time, use:

```bash
streamlit run app.py
```

Enjoy the match, and good luck being the last survivor! 🏆
