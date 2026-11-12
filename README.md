# Release Desk

A local dashboard that keeps everything a game needs for its stores in one place: the listing text and art, builds, per-store setup steps, key status and a run log. It is reusable across projects; each project keeps its own data in a `Store/` folder.

Status: design and clickable mockup (`prototypes/dashboard.html`). Nothing is implemented yet.

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
- **Linking:** a local, ignored `projects.json` in the desk maps each game to its Unity project path and store-data path. Store-data repos are not submodules of this public repo, so public clones never point at private repos.
- **Traceability:** each upload records the game's commit and the store-data commit in the log.

```
<game>-store/            private store-data repo
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
