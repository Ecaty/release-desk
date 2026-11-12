# Release Desk

A local dashboard that keeps everything a game needs for its stores in one place: the listing text and art, builds, per-store setup steps, key status and a run log. It is reusable across projects; each project keeps its own data in a `Store/` folder.

Status: Steam works end to end up to the upload (plus screenshot capture) (listing, art and screenshot checks, Unity settings sync, Windows build, SteamPipe upload with preview). Epic and Google Play are next. Design mockup: `prototypes/dashboard.html`.

## Use

1. In the game's Unity project, add the package to `Packages/manifest.json`:
   `"com.release-desk.unity": "https://github.com/Ecaty/release-desk.git?path=/unity"`
2. Add the game's private store data as a `Store/` folder (or submodule) in the project root with a `store.json`.
3. Run `Start-Desk.cmd [path-to-unity-project]` (Python 3.10+, no packages needed) and open http://127.0.0.1:27760/.
4. Keep the Unity Editor open on the project for Push to Unity, builds and screenshots.

## Screenshots

`Store/shots.json` lists shots (`name`, `stores`, `width`, `height`, `wait`, `setup`). The desk asks Unity to enter Play mode; for each shot it calls the game's `IShotStage.Prepare(shot)` (the game decides what `setup` means, for example Flecs Script), renders that camera off-screen at the exact size (no UI) and writes `Store/shots/<store>/<name>.png`. The game implements `ReleaseDesk.Editor.IShotStage` once.

## Icons

Put one square icon at `Store/art/icon.png` (1024×1024 PNG, transparent background allowed). **Make icons** (Steam > Listing > Art) writes every store size from it with the desk's own image code (no packages): Steam shortcut icon `steam/art/shortcut_icon.ico` (256, 48, 32, 16), Steam app icon `steam/art/app_icon.jpg` (184), Google Play `play/art/icon.png` (512). Which outputs exist comes from `"make": "icon"` entries in `rules/<store>.json`.

## What it does

- **One page per store.** Each store page has its own Listing (text and art in that store's sizes), Builds and Setup steps, so a release focuses on one store at a time. The game name is the shared default each page starts from.
- **Unity stays in sync.** Product Name, version, icon and Android package are pushed into the Unity project through the Unity CLI.
- **Automates what the stores allow.** Set up / Refresh runs every step it can and lists the rest as short manual steps with links.
- **Copy-paste for the rest.** Where a store has no API for its page, each field has a Copy button (text or file path).
- **Log for humans and agents.** Every run writes a short summary to the project's `Logs/latest.txt`: what passed, what is missing, what blocks a release.

## What each store allows (to verify when implementing)

| Store | Builds | Listing text and art | Notes |
|---|---|---|---|
| Google Play | Play Developer API (AAB to a track) | Play Developer API | New personal accounts must run a closed test before production. |
| Steam | SteamCMD with an app build script | Steamworks site only (no public API) | Build-only Steam account for uploads. Valve reviews page and build. |
| Epic Games Store | BuildPatch Tool | Epic Developer Portal only | Needs an approved developer organization. |

Store rules (field limits, image sizes, required assets) live in one rules file per store with the source URL and the date they were last checked. A refresh warns when a rules file is older than 60 days.

## Repositories

- **release-desk (this repo, public):** the desk's code and the Unity package. No game data.
- **Store data (one private repo per game):** listing text, art, screenshots, capture list. Private because unreleased text and art should not sit in a public game repo.
- **The game's Unity project:** references the desk's Unity package by Git URL (`.../release-desk.git?path=/unity`), which adds the Editor entry points the desk calls (apply PlayerSettings, capture screenshots, build). The game repo holds no store data.
- **Linking:** the desk takes only the Unity project folder and finds `Store/` inside it. In this setup `Store/` is a private submodule of the game repo; public clones of the game simply skip it. Recent projects are remembered in `%APPDATA%
elease-desk\config.json`.
- **Traceability:** each upload records the game's commit and the store-data commit in the log.

```
Store/                   private store-data repo, submodule in the game's root
  store.json             shared defaults: name, version, package/app ids (no secrets)
  shots.json             screenshot capture list: scene, camera, world, sizes
  steam/ epic/ play/     per-store text (listing.json) and art (Git LFS)
  shots/                 captured screenshots (Git LFS)
  Logs/latest.txt        last run summary (ignored)
```

## Secrets

The desk never shows or stores secret values; it only checks that each one exists.

- Android upload keystore: outside the repo (default `%USERPROFILE%\.release-keys\`). Passwords in Windows Credential Manager. Google Play App Signing keeps the release key.
- Play service account JSON: outside the repo, path in `PLAY_SERVICE_ACCOUNT_JSON`.
- Steam build login and Epic client secret: Windows Credential Manager.
- Unity reads keystore path and passwords at build time; nothing is written into ProjectSettings.
- If builds later run in CI, the same names map to GitHub Actions secrets.

## Planned shape

- Local web app on `127.0.0.1`, started from a script; no hosted server.
- Unity side: a small Editor entry point in the game project (apply PlayerSettings, capture screenshots, build) called through the Unity CLI.
- Store adapters, one per store, each with `check` (read-only), `refresh` (apply) and its rules file.
- Store pages in the desk: Steam, Epic Games Store, Google Play.
- Implementation order: Google Play first end to end (fully automatable, matches the Android test phone), then Steam builds, then Epic builds.

## Later

- **Branch builds:** a Refresh that lists the game's branches (a small branch view) with a Build button per branch. The branch is checked out in place in the game project: the desk refuses when there are uncommitted changes or unsaved scenes, waits for Unity to reimport, builds, and switches back to the previous branch afterwards.
- **Build machine:** if the main PC should stay free during builds, a GitHub Actions self-hosted runner on a second machine can build a chosen branch; the desk would start the run and collect the result. Only manual runs and the owner's pushes may trigger it (the game repo is public).
