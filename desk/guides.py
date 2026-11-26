"""Click-by-click guides for the by-hand steps of the PC and Galaxy stores: the direct link first, then at most 4 short
clicks. Applied by step title on top of each store's status (Google Play and itch.io keep theirs in their own modules).
Labels as the portals showed them in Nov 2026; the page asks for a screenshot when one looks different."""

STEAM = "https://partner.steamgames.com"
EPIC = "https://dev.epicgames.com/portal"
GOG = "https://devportal.gog.com"
PARTNER = "https://partner.microsoft.com/dashboard"
SELLER = "https://seller.samsungapps.com"

GUIDES = {
    "steam": {
        "Steamworks account and app": [
            {"text": "Press Join Steamworks, sign in with your Steam account.", "link": STEAM + "/steamdirect"},
            {"text": "Fill in bank, tax and identity details. Pay the US$100 app fee (paid back after US$1,000 in sales)."},
            {"text": "Open the new app: copy its App ID, and from SteamPipe > Depots the Windows depot ID.", "link": STEAM + "/dashboard"},
            {"text": "Paste both into Keys & accounts here, Save.", "go": "steam/keys/ids-steam-appId"},
        ],
        "Build account": [
            {"text": "Make a second Steam account just for uploads.", "link": "https://store.steampowered.com/join"},
            {"text": "Steamworks: Users & Permissions > Manage Users > Invite New User, type its email.", "link": STEAM + "/dashboard"},
            {"text": "Give it only Edit App Metadata and Publish App Changes To Steam."},
            {"text": "Type its account name in Keys & accounts here, Save.", "go": "steam/keys/steam-user"},
        ],
        "SteamCMD installed and logged in once": [
            {"text": "Press Install SteamCMD here.", "go": "steam/keys/steamcmd"},
            {"text": "Open PowerShell, paste the command shown above, Enter."},
            {"text": "Type the build account's password and Steam Guard code there. The desk never sees them."},
        ],
        "Store page text": [
            {"text": "Open your app, press Edit Store Page.", "link": STEAM + "/dashboard"},
            {"text": "Copy each field here and paste it into the same field there.", "go": "steam/listing/steam-text"},
            {"text": "Press Save at the bottom."},
        ],
        "Store art": [
            {"text": "Open your app > Edit Store Page > Graphical Assets.", "link": STEAM + "/dashboard"},
            {"text": "Upload each image from Store/steam/art (Listing > Art shows which is which).", "go": "steam/listing/steam-art"},
        ],
        "Screenshots": [
            {"text": "Open your app > Edit Store Page > Screenshots.", "link": STEAM + "/dashboard"},
            {"text": "Upload 5 or more from Store/shots/steam.", "go": "steam/listing/steam-shots"},
        ],
        "Review by Valve": [
            {"text": "Open your app > Content Survey: answer it (it asks about AI content).", "link": STEAM + "/dashboard"},
            {"text": "SteamPipe > Builds: set the build live on default, play it through Steam for 5 minutes."},
            {"text": "Mark the store page and the build ready for review. Coming Soon must be public 2 weeks before release."},
        ],
    },
    "epic": {
        "Epic developer organization and product": [
            {"text": "Sign in, create the organization.", "link": EPIC},
            {"text": "Create product: the game's name. Pay US$100 (per product, non-refundable; paid back after US$1,000 in Epic sales)."},
            {"text": "Product Settings: copy organization, product and artifact IDs into Keys & accounts here, Save.", "go": "epic/keys/ids-epic-organizationId"},
        ],
        "BuildPatch Tool": [
            {"text": "Open your product > Epic Games Store > Artifacts and Binaries > Download build patch tool.", "link": EPIC},
            {"text": "Unzip it into the folder Keys & accounts shows.", "go": "epic/keys/epic-bpt"},
        ],
        "BPT credentials": [
            {"text": "Open your product > Product Settings > BPT credentials, create one.", "link": EPIC},
            {"text": "Paste the client ID into Keys & accounts here.", "go": "epic/keys/epic-secret"},
            {"text": "Press Save BPT secret and paste the secret in the window that opens. The desk keeps it in Credential Manager."},
        ],
        "Store page text": [
            {"text": "Open your product > Epic Games Store > Store Presence > Pages.", "link": EPIC},
            {"text": "Copy each field here and paste it there.", "go": "epic/listing/epic-text"},
            {"text": "Save."},
        ],
        "Store art": [
            {"text": "Open your product > Store Settings: upload the logo.", "link": EPIC},
            {"text": "Offers: upload the offer images from Store/epic/art.", "go": "epic/listing/epic-art"},
        ],
        "Media carousel": [
            {"text": "Open your product > Store Presence > Pages > media carousel.", "link": EPIC},
            {"text": "Upload 5 screenshots from Store/shots/epic.", "go": "epic/listing/epic-shots"},
        ],
        "Attach, rate and submit": [
            {"text": "Open your product > Artifacts and Binaries: attach the uploaded binary to Windows.", "link": EPIC},
            {"text": "Set regions, age ratings and price."},
            {"text": "Submit for review, then promote it in Release Management."},
        ],
    },
    "gog": {
        "Submit the game to GOG": [
            {"text": "Read how to submit, and send the game when it's nearly done.", "link": "https://support.gog.com/hc/en-us/articles/11382878039197"},
            {"text": "Wait for GOG's answer by email. The Developer Portal opens only after GOG invites you."},
            {"text": "After signing: paste the product ID into Keys & accounts here, Save.", "go": "gog/keys/ids-gog-productId"},
        ],
        "Pipeline Builder": [
            {"text": "Developer Portal > GOG GALAXY Components: download Pipeline Builder.", "link": GOG},
            {"text": "Unzip it into the folder Keys & accounts shows.", "go": "gog/keys/gog-tool"},
        ],
        "Build Creator project": [
            {"text": "Open GOG's Build Creator, make a new project.", "link": GOG},
            {"text": "Depot folder: Build/GOG/Windows inside the Unity project."},
            {"text": "Save it as Store/gog/project.json.", "go": "gog/keys/gog-project"},
        ],
        "Store page text": [
            {"text": "Copy the text here; GOG asks for it with the assets.", "go": "gog/listing/gog-text"},
        ],
        "Key art and logo": [
            {"text": "Developer Portal > Assets Manager.", "link": GOG},
            {"text": "Upload key art and logo as layered .psd files, 1920x1080 or larger, from Store/gog/art.", "go": "gog/listing/gog-art"},
        ],
        "Screenshots": [
            {"text": "Developer Portal > Assets Manager.", "link": GOG},
            {"text": "Upload screenshots from Store/shots/gog.", "go": "gog/listing/gog-shots"},
        ],
        "Ratings, prices and release": [
            {"text": "Developer Portal: your product's page.", "link": GOG},
            {"text": "Agree age ratings, prices, release date and launch discount with your GOG contact."},
        ],
    },
    "microsoft": {
        "Partner Center account and app name": [
            {"text": "Sign up as a Windows app developer (personal), pay the fee if asked.", "link": "https://developer.microsoft.com/microsoft-store/register"},
            {"text": "Partner Center > Apps and games > + New product > reserve the game's name.", "link": PARTNER},
            {"text": "Product management > Product identity: copy Store ID, Package/Identity/Name, Publisher, Publisher display name."},
            {"text": "Paste them into Keys & accounts here, Save.", "go": "microsoft/keys/ids-microsoft-productId"},
        ],
        "Packaging tool": [
            {"text": "Download and install the Windows SDK.", "link": "https://developer.microsoft.com/windows/downloads/windows-sdk/"},
            {"text": "Back here, Keys & accounts shows makeappx found.", "go": "microsoft/keys/microsoft-tools"},
        ],
        "Store listing text": [
            {"text": "Open your game > Store listings > English.", "link": PARTNER},
            {"text": "Copy each field here and paste it there.", "go": "microsoft/listing/microsoft-text"},
            {"text": "Save."},
        ],
        "Store images": [
            {"text": "Open your game > Store listings > English > Store logos.", "link": PARTNER},
            {"text": "Upload the 2:3 poster and the 300x300 icon from Store/microsoft/art.", "go": "microsoft/listing/microsoft-art"},
        ],
        "Screenshots": [
            {"text": "Open your game > Store listings > English > Screenshots.", "link": PARTNER},
            {"text": "Upload screenshots from Store/shots/microsoft.", "go": "microsoft/listing/microsoft-shots"},
        ],
        "First submission by hand": [
            {"text": "Open your game > Start your submission.", "link": PARTNER},
            {"text": "Packages: upload the MSIX from Builds. Fill in Pricing, Properties and Age ratings."},
            {"text": "Submit to the Store. Wait until it is published; the desk sends updates after that."},
        ],
    },
    "samsung": {
        "Seller Portal account": [
            {"text": "Sign up for a free seller account (no Samsung phone needed).", "link": SELLER},
        ],
        "Register the app by hand": [
            {"text": "Add New Application > Android: the game's name.", "link": SELLER},
            {"text": "Upload the release AAB, fill in the listing, screenshots, age rating, countries."},
            {"text": "Submit. Then copy its 12-digit content ID into Keys & accounts here.", "go": "samsung/keys/ids-samsung-contentId"},
        ],
        "Service account": [
            {"text": "Seller Portal > Assistance > API Service > Create Service Account (Publishing & ITEM).", "link": SELLER},
            {"text": "Save the private key file outside every project."},
            {"text": "Set SAMSUNG_SERVICE_ACCOUNT_KEY to its path (like the Google Play key), and paste the service account ID here.", "go": "samsung/keys/ids-samsung-serviceAccountId"},
        ],
        "App icon": [
            {"text": "Seller Portal > your app > Display: upload the 512x512 icon from Listing > Art.", "link": SELLER},
        ],
    },
}


def apply(store_id, status):
    """Adds the guide for each by-hand step that has one; the step's own guide wins."""
    for step in status.get("steps", []):
        g = GUIDES.get(store_id, {}).get(step["title"])
        if g and not step.get("guide"):
            step["guide"] = g
    return status
