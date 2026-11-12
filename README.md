# Release Desk

A local dashboard that keeps everything a game needs for its stores in one place: the listing text and art, builds, per-store setup steps, key status and a run log. It is reusable across projects; each project keeps its own data in a `Store/` folder.

Status: design and clickable mockup (`prototypes/dashboard.html`). Nothing is implemented yet.

## What it does

- **One listing, many stores.** Title, descriptions, icon, screenshots and version live as files in the project's `Store/` folder (versioned with the game). Editing them in the desk updates Unity (Product Name, version, icon, Android package) through the Unity CLI.
- **Automates what the stores allow.** For each store a Set up / Refresh button runs every step it can and lists the rest as short manual steps with links.
- **Copy-paste for the rest.** Where a store has no API for its page, each field has a Copy button (text or file path).
- **Log for humans and agents.** Every run writes a short summary to `Store/Logs/latest.txt` (ignored by Git): what passed, what is missing, what blocks a release.

## What each store allows (to verify when implementing)

| Store | Builds | Listing text and art | Notes |
|---|---|---|---|
| Google Play | Play Developer API (AAB to a track) | Play Developer API | First target. New personal accounts must run a closed test before production. |
| Steam | SteamCMD with an app build script | Steamworks site only (no public API) | Build-only Steam account for uploads. Valve reviews page and build. |
| Epic Games Store | BuildPatch Tool | Epic Developer Portal only | Needs an approved developer organization. |

Store rules (field limits, image sizes, required assets) live in one rules file per store with the source URL and the date they were last checked. A refresh warns when a rules file is older than 60 days.

## Project data (`Store/` in each game repo)

```
Store/
  store.json        name, descriptions, version, package/app ids per store (no secrets)
  shots.json        screenshot capture list: scene, camera, world, sizes
  icon.png          source icon
  art/              feature graphic, capsules, etc. (Git LFS)
  shots/            captured screenshots (Git LFS)
  Logs/latest.txt   last run summary (ignored)
```

Store data stays in the game repo, not a separate submodule, so a listing change and the build it describes land in the same commit.

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
- Order: Google Play first, end to end; then Steam builds; then Epic builds.
