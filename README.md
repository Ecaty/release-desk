# Release Desk

A local dashboard that keeps everything a game needs for its stores in one place: the listing text and art, builds, per-store setup steps, key status and a run log. It is reusable across projects; each project keeps its own data in a `Store/` folder.

Status: seven stores are wired up: Steam (upload with SteamCMD), itch.io (butler), Epic Games Store (BuildPatch Tool), GOG (Pipeline Builder), Microsoft Store (MSIX + msstore CLI), Google Play (Play Developer API) and Samsung Galaxy Store (Galaxy Store Developer API, same AAB as Play). Each has listing and art checks, its own Windows or Android build and setup steps that jump to the field that finishes them. Real uploads to itch.io, Epic, GOG, Microsoft, Play and Galaxy Store wait for their developer accounts. Design mockup: `prototypes/dashboard.html`.

## Use

1. In the game's Unity project, add the package to `Packages/manifest.json`:
   `"com.release-desk.unity": "https://github.com/Ecaty/release-desk.git?path=/unity"`
2. Add the game's private store data as a `Store/` folder (or submodule) in the project root with a `store.json`.
3. Run `Start-Desk.cmd [path-to-unity-project]` (Python 3.10+, no packages needed) and open http://127.0.0.1:27760/.
4. Push to Unity, builds and screenshots use the project's Unity Editor; if it is closed, the desk opens the project's Unity version and waits until it is ready (never a second Editor on the same project). Every run has **Cancel**: it stops waiting and ends the desk's own child processes (SteamCMD, BuildPatch Tool, adb); a build already running inside Unity is cancelled in Unity's progress window.

## Screenshots

`Store/shots.json` lists shots (`name`, `stores`, `width`, `height`, `wait`, `setup`). The desk asks Unity to enter Play mode; for each shot it calls the game's `IShotStage.Prepare(shot)` (the game decides what `setup` means, for example Flecs Script), renders that camera off-screen at the exact size (no UI) and writes `Store/shots/<store>/<name>.png`. The game implements `ReleaseDesk.Editor.IShotStage` once.

## itch.io

- Open to everyone, no review or fee. Create the project page on itch.io and put `user/game` (and the channel, `windows` by default) in Keys & accounts. Disclose generative AI use on the Edit game page (Code), as itch.io's quality guidelines ask.
- **Upload:** unzip butler (itch.io's official tool) into `%APPDATA%\release-desk\butler` or put it on PATH; **Log in to itch.io** runs `butler login` in its own console and butler keeps the login. **Push** runs `butler push Build/Itch/Windows user/game:windows --userversion <version>+<build> --if-changed` with debug files ignored; only changes are sent. **Push preview** runs `butler push-preview` and sends nothing.
- **Page:** tagline and description (Copy), 630×500 cover (Make capsules) and 3 to 5 screenshots in `Store/shots/itch`, added on Edit game.

## Epic Games Store

- **Setup:** put `organizationId`, `productId`, `artifactId` and the BPT `clientId` under `"epic"` in `Store/store.json`; unzip the BuildPatch Tool (Developer Portal > Artifacts and Binaries) into `%APPDATA%\release-desk\BuildPatchTool`; **Save BPT secret** (Keys & accounts) opens a console where `cmdkey` stores the client secret as `release-desk/epic/<productId>/bpt-secret`.
- **Upload:** **Build Windows** (Epic tab) builds into `Build/Epic/Windows`; **Upload to Dev sandbox** runs BPT `UploadBinary` with build version `<version>-b<build>-<commit>` and an ignore list for debug files. A PowerShell helper reads the secret from Credential Manager into BPT's own environment (`-ClientSecretEnvVar`), so the desk never holds it. **Check connection** runs `ListBinaries` and changes nothing. Output goes to `Store/Logs/buildpatchtool.txt`.
- **Listing and art:** no public store-page API, so each field has Copy. Sizes from Epic's Storefront Media Guide: product logo 960×540 PNG (made from the logo), offer images 2560×1440 and 1200×1600 and social preview 1200×1200 (made from key art + logo), media carousel screenshots 1920×1080 in `Store/shots/epic` (add `"epic"` to a shot's stores).
- **By hand:** organization and product, attaching the binary to the artifact's Windows platform, regions and age ratings, price, review submission and Release Management.

## GOG

- GOG curates its catalogue: submit the game first. After signing, put the product ID (and an optional upload branch) in Keys & accounts.
- **Build:** Build Windows (GOG tab) builds into `Build/GOG/Windows`; GOG builds must run without another store's client or DRM.
- **Upload:** unzip Pipeline Builder (Developer Portal) into `%APPDATA%\release-desk\GOGGalaxyPipelineBuilder`, make the project once in GOG's Build Creator with depot folder `Build/GOG/Windows` and save it as `Store/gog/project.json`. **Upload with Pipeline Builder** runs `build-game` with the release version, an ignore list for debug files and the branch, in its own console so the tool can ask for the GOG login the first time (it caches it). Publish the uploaded build to a branch in the Developer Portal.
- **Store page:** description, system requirements and legal lines (Copy), key art and logo (Make capsules; GOG asks for 1920×1080 or larger) and screenshots go to GOG through their Assets Manager.

## Microsoft Store

- **First release by hand** in Partner Center (the CLI cannot create it): reserve the name, copy the Store ID and Product identity values into Keys & accounts, upload the first MSIX, age ratings, pricing and listing.
- **Package MSIX:** copies the Windows build (`Build/Microsoft/Windows`) to a staging folder with a generated `AppxManifest.xml` (full-trust desktop app, identity from Keys & accounts, version `major.minor.build.0`, microphone capability) and logos made from the icon, then runs `makeappx` from the Windows SDK. The Store signs packages it distributes.
- **Publish update:** `msstore publish <msix> -id <Store ID>` with the Microsoft Store Developer CLI; **Set up msstore** opens its own console for the Partner Center API values, so the desk never sees them. Microsoft's CLI currently updates free products only.
- **Listing:** description (Copy), 2:3 poster art 1440×2160 and 1:1 box art 2160×2160 (key art + logo), 300×300 tile icon (from the icon), 16:9 super hero art 3840×2160 without text, screenshots 1366×768 or larger in `Store/shots/microsoft`.

## Google Play

- **Upload key:** Keys & accounts > Create upload key opens a console: Unity's `keytool` creates `%USERPROFILE%\.release-keys\<package>-upload.jks` (alias `upload`) and `cmdkey` stores the password as `release-desk/<package>/upload-key` in Windows Credential Manager. Both ask for the password in that console; the desk only checks that the file and the entry exist. Back the keystore up outside every repository; Play App Signing keeps the release key.
- **Release AAB:** the Unity package reads the password from Credential Manager inside the Editor for that build only and restores the previous keystore settings afterwards; nothing is written to ProjectSettings.
- **Publish:** one Play Developer API edit uploads the newest release AAB to the track with What's new as release notes, the listing text (`Store/play/listing.json`, title = release name), icon, feature graphic and phone screenshots (`Store/shots/play`). Preview validates and then deletes the edit. Sign-in uses the service account JSON at `PLAY_SERVICE_ACCOUNT_JSON`; the token request is signed with the desk's own RS256 code (no packages). `Store/store.json` `"play": {"track": "internal", "status": "draft"}` sets the track and release status (draft waits for a click in Play Console).
- **Track and checks:** the Builds tab chooses the track (internal, closed, open, production) and whether a release is a draft or rolls out; **Check Play** lists each track's releases and the highest version code without changing anything. After a successful publish the build number goes up by one (the Play override if it has one, else the shared number).
- **By hand once:** developer account, creating the app and its first upload in Play Console, content rating, data safety and target audience, and the closed test new personal accounts need before production.

## Galaxy Store

- Same release AAB as Google Play; Galaxy Store makes a universal APK from it (Play Asset Delivery is not supported). No Samsung device is needed: Samsung reviews on its own devices.
- **By hand once:** seller account, registering the app with its listing, screenshots, age rating, countries and signing choice in Seller Portal (the API cannot register apps). Put the 12-digit content ID and the service account ID in Keys & accounts; save the service account's private key outside every repository with its path in `SAMSUNG_SERVICE_ACCOUNT_KEY`.
- **Submit update:** signs a JWT with the key (desk's own RS256), uploads the AAB in an upload session, opens an update with What's new, registers the binary with the previous binary's device targeting, and submits for review. **Check Galaxy Store** only reads the app's status.

## Release

One release is shared by every store: game name, short description, description, version, build number and What's new (a short change list) in `Store/store.json` (keys `name`, `short`, `description`, `version`, `build`, `whatsNew`), edited on Overview. Store listing fields marked `"from"` in `rules/<store>.json` show these values (Steam short description and About, Play short and full description, Epic About, GOG and Microsoft description, itch.io tagline and description); when the shared text is over a store's limit (Play short description 80, Steam 300, Play full 4000, Epic and Microsoft 10000, Play title 30), Overview and that store's page flag it so it gets an override. Each store page shows the same fields with an **override** box; a ticked field keeps that store's own value in `"overrides": {"<store>": {...}}`, an unticked one uses the shared value. **Fill from commits** collects player-facing notes since the last build: commits that change something players or a store would notice end their message with a Git trailer such as `Release-note: New aquarium world with schooling fish` (one line per note); technical commits have none and never show up. Before each build the desk pushes that store's values to Unity, and the build history keeps the change list. **Build all** (Overview) builds the chosen kinds one after another. Store marks in the page are from Simple Icons (CC0, `web/icons/`); the trademarks belong to their owners. Every other icon is a Google Material Symbol (Apache 2.0) from `web/fonts/material-symbols.woff2`, a subset that holds only the icons the page uses, so the desk works offline. To add an icon, fetch the subset again from Google Fonts with the new name added to `icon_names` (`fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..24,400,0..1,0&icon_names=...`, names sorted) and replace the woff2.

## Capsules

Steam capsules (and the Play feature graphic) are made from two sources, never generated by AI:

- **Key art:** a shot named `key-art` in `Store/shots.json` with `"stores": ["art"]` at 3840×2160, set up by its Flecs Script like any screenshot. Unity writes `Store/shots/art/key-art.png`.
- **Logo:** `Store/art/logo.png`, a transparent PNG at least 1280 wide.

**Make capsules** (Steam > Listing > Art) crops the key art to each size in `rules/<store>.json` (`"make": "capsule"` adds the logo, `"hero"` is art only, `"logo"` is the logo alone) and places the logo in its box. Tune per output in `Store/art.json`: `{"outputs": {"steam/header_capsule": {"focus": [0.5, 0.4], "zoom": 1.1, "logo": {"x": 0.5, "y": 0.5, "w": 0.6, "h": 0.5}}}}` (focus = point of the key art to keep centred, 0..1; logo box = centre and maximum size as fractions of the output). The full set from 3840×2160 key art takes about a minute and a half (pure Python).

## Icons

Put one square icon at `Store/art/icon.png` (1024×1024 PNG, transparent background allowed). **Make icons** (Steam > Listing > Art) writes every store size from it with the desk's own image code (no packages): Steam shortcut icon `steam/art/shortcut_icon.ico` (256, 48, 32, 16), Steam app icon `steam/art/app_icon.jpg` (184), Google Play `play/art/icon.png` (512). Which outputs exist comes from `"make": "icon"` entries in `rules/<store>.json`.

## What it does

- **Progress you can walk.** Each store page shows its setup progress; the arrows step through the open steps and land on the exact field, box or button that finishes each one (Setup steps has a Go button per step). Each page keeps its sections as tabs (Listing, Builds, Keys & accounts, Setup steps), with subtabs such as Release, Text, Art and Screenshots; a red dot marks a tab with something to fix. Store IDs, tools and logins are in each store's Keys & accounts tab.
- **One page per store.** Each store page has its own Listing (text and art in that store's sizes), Builds and Setup steps, so a release focuses on one store at a time. The game name is the shared default each page starts from.
- **Unity stays in sync.** Product Name, version, icon and Android package are pushed into the Unity project through the Unity CLI.
- **Automates what the stores allow.** Set up / Refresh runs every step it can and lists the rest as short manual steps with links.
- **Copy-paste for the rest.** Where a store has no API for its page, each field has a Copy button (text or file path).
- **Log for humans and agents.** Every run writes a short summary to the project's `Logs/latest.txt`: what passed, what is missing, what blocks a release. Overview > Log shows it with each tool's log and earlier runs.

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
- **Linking:** the desk takes only the Unity project folder and finds `Store/` inside it. In this setup `Store/` is a private submodule of the game repo; public clones of the game simply skip it. Recent projects are remembered in `%APPDATA%\release-desk\config.json`.
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

- **Apple App Store:** needs a Mac with Xcode to build and sign, and review of the downloaded-recipe question (guideline 2.5.2); see the game's distribution notes.

- **Branch builds:** a Refresh that lists the game's branches (a small branch view) with a Build button per branch. The branch is checked out in place in the game project: the desk refuses when there are uncommitted changes or unsaved scenes, waits for Unity to reimport, builds, and switches back to the previous branch afterwards.
- **Build machine:** if the main PC should stay free during builds (candidate: a laptop with an i7-4500U, 2 cores, 16 GB, so expect builds a few times slower than the main PC), a GitHub Actions self-hosted runner on a second machine can build a chosen branch; the desk would start the run and collect the result. Only manual runs and the owner's pushes may trigger it (the game repo is public).
