# Apple Code Signing

One-time provisioning of Apple signing secrets for macOS app repos.
Two scripts: a seed script (interactive, run once per machine) and a push
script (non-interactive, run once per repo). The skill probes keychain
state during audit and generates only what's needed.

## Table of Contents

- [Audit-Phase Probe Logic](#audit-phase-probe-logic)
- [Seed Script Template](#seed-script-template)
- [Push Script Template](#push-script-template)
- [Secret Reference](#secret-reference)
- [Rotation](#rotation)
- [Known Quirks](#known-quirks)

---

## Audit-Phase Probe Logic

Run these three commands when a macOS app target is detected. All are
read-only.

```bash
# 1. Developer ID Application cert present?
cert_count=$(security find-identity -v -p codesigning 2>/dev/null \
  | grep -c "Developer ID Application")

# 2. APPLE_ID seeded?
security find-generic-password -s "apple-developer-signing" -a "APPLE_ID" -w &>/dev/null
# exit 0 = present, exit 44 = missing

# 3. APPLE_APP_SPECIFIC_PASSWORD seeded?
security find-generic-password -s "apple-developer-signing" -a "APPLE_APP_SPECIFIC_PASSWORD" -w &>/dev/null
```

### Decision Matrix

| Cert count | APPLE_ID | APPLE_APP_SPECIFIC_PASSWORD | Generate seed? | Generate push? |
|---|---|---|---|---|
| >=1 | present | present | no | yes |
| any | any gap | any gap | yes | yes |
| 0 | any | any | yes (cert-import path) | yes |

### Audit Report Format

When the keychain has gaps:

```
Apple code signing
------------------
  OK Developer ID Application cert found (team TEAMID)
  -- APPLE_ID missing from keychain
  -- APPLE_APP_SPECIFIC_PASSWORD missing from keychain

  Will generate:
    scripts/seed-apple-keychain.sh   (one-time, prompts for missing values)
    scripts/push-apple-secrets.sh    (pushes secrets to this repo)

  First run: ./scripts/seed-apple-keychain.sh && ./scripts/push-apple-secrets.sh
```

When fully seeded:

```
Apple code signing
------------------
  OK Developer ID Application cert found (team TEAMID)
  OK APPLE_ID cached in keychain
  OK APPLE_APP_SPECIFIC_PASSWORD cached in keychain

  Will generate:
    scripts/push-apple-secrets.sh    (pushes secrets to this repo)

  Run: ./scripts/push-apple-secrets.sh
```

When no cert is found, report it as missing and include guidance in the
seed script about importing one.

---

## Seed Script Template

Generated as `scripts/seed-apple-keychain.sh`. Only generated when the
keychain probe finds gaps. Idempotent -- safe to re-run.

```bash
#!/usr/bin/env bash
# ABOUTME: One-time interactive seeder for the apple-developer-signing keychain
# ABOUTME: service. Run once per machine; future macOS apps reuse the cached values.
set -euo pipefail

SERVICE="apple-developer-signing"

probe() { security find-generic-password -s "$SERVICE" -a "$1" -w &>/dev/null; }
store() { security add-generic-password -U -s "$SERVICE" -a "$1" -w "$2"; }

echo "Checking Apple signing prerequisites..."
echo

# -- Developer ID Application identity --

cert_line=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep "Developer ID Application" | head -1 || true)

if [[ -z "$cert_line" ]]; then
    cat <<'EOF'
No Developer ID Application certificate found in your login keychain.

To get one:
  1. Visit https://developer.apple.com/account/resources/certificates/list
  2. Create or download a "Developer ID Application" certificate
  3. Double-click the .cer to import it into Keychain Access
  4. Verify the matching private key is in your login keychain
     (expand the cert in "My Certificates" -- the private key should appear beneath it)
  5. Re-run this script
EOF
    exit 1
fi

team_id=$(echo "$cert_line" | sed -E 's/.*\(([A-Z0-9]{10})\).*/\1/')
echo "OK  Developer ID Application cert found (team $team_id)"

# -- APPLE_ID --

if probe APPLE_ID; then
    echo "OK  APPLE_ID already cached"
else
    default_email="$(git config user.email 2>/dev/null || true)"
    read -r -p "Apple ID email${default_email:+ [$default_email]}: " apple_id
    apple_id="${apple_id:-$default_email}"
    [[ -z "$apple_id" ]] && { echo "Apple ID is required" >&2; exit 1; }
    store APPLE_ID "$apple_id"
    echo "OK  APPLE_ID stored"
fi

# -- APPLE_APP_SPECIFIC_PASSWORD --

if probe APPLE_APP_SPECIFIC_PASSWORD; then
    echo "OK  APPLE_APP_SPECIFIC_PASSWORD already cached"
else
    cat <<'EOF'

Generate an app-specific password (notarytool needs one):
  1. Visit https://appleid.apple.com/account/manage
  2. Sign in with your Apple ID
  3. Sign-In and Security -> App-Specific Passwords -> Generate Password
  4. Label it something like "notarytool" or "github-actions"
  5. Copy the password -- Apple only shows it ONCE

One app-specific password works for all your apps. You do not need a
separate one per project.
EOF
    echo
    read -r -s -p "Paste app-specific password: " asp
    echo
    [[ -z "$asp" ]] && { echo "Password is required" >&2; exit 1; }
    store APPLE_APP_SPECIFIC_PASSWORD "$asp"
    echo "OK  APPLE_APP_SPECIFIC_PASSWORD stored"
fi

echo
echo "Keychain seeded. Next: ./scripts/push-apple-secrets.sh"
```

---

## Push Script Template

Generated as `scripts/push-apple-secrets.sh`. Always generated for macOS
app repos. Non-interactive (except the one-time "Always Allow" keychain
prompt on first cert export). `{OWNER}` and `{REPO}` are replaced by the
skill at generation time.

```bash
#!/usr/bin/env bash
# ABOUTME: Pushes Apple signing secrets from the apple-developer-signing keychain
# ABOUTME: service to this repo's GitHub Actions secrets. Idempotent.
set -euo pipefail

SERVICE="apple-developer-signing"
OWNER="{OWNER}"
REPO="{REPO}"

DRY_RUN=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --force)   FORCE=1 ;;
        -h|--help) echo "Usage: $0 [--dry-run] [--force]"; exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# -- Preflight --

command -v gh >/dev/null || { echo "Error: gh CLI required. Install with: brew install gh" >&2; exit 1; }
gh auth status &>/dev/null || { echo "Error: not authenticated with gh. Run: gh auth login" >&2; exit 1; }

# -- Check existing secrets on GitHub --

existing=$(gh secret list --repo "$OWNER/$REPO" --json name -q '.[].name' 2>/dev/null || true)

want=(APPLE_ID APPLE_TEAM_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_CERTIFICATE APPLE_CERTIFICATE_PASSWORD)
missing=()
for name in "${want[@]}"; do
    if [[ "$FORCE" == 1 ]] || ! grep -Fxq "$name" <<<"$existing"; then
        missing+=("$name")
    fi
done

if [[ ${#missing[@]} -eq 0 ]]; then
    echo "All Apple secrets already set on $OWNER/$REPO. Use --force to overwrite."
    exit 0
fi

echo "Will set on $OWNER/$REPO: ${missing[*]}"

if [[ "$DRY_RUN" == 1 ]]; then
    echo "(dry run -- not reading keychain, not calling gh secret set or security export)"
    exit 0
fi

# -- Read keychain --

apple_id=$(security find-generic-password -s "$SERVICE" -a APPLE_ID -w 2>/dev/null) \
    || { echo "APPLE_ID not in keychain. Run ./scripts/seed-apple-keychain.sh first" >&2; exit 1; }
asp=$(security find-generic-password -s "$SERVICE" -a APPLE_APP_SPECIFIC_PASSWORD -w 2>/dev/null) \
    || { echo "APPLE_APP_SPECIFIC_PASSWORD not in keychain. Run ./scripts/seed-apple-keychain.sh first" >&2; exit 1; }

# -- Derive team ID from cert --

team_line=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep "Developer ID Application" | head -1)
[[ -z "$team_line" ]] && { echo "No Developer ID Application identity in keychain" >&2; exit 1; }
team_id=$(echo "$team_line" | sed -E 's/.*\(([A-Z0-9]{10})\).*/\1/')

echo "Using team ID: $team_id"

# -- Export cert if needed --

need_cert=0
for name in "${missing[@]}"; do
    [[ "$name" == APPLE_CERTIFICATE || "$name" == APPLE_CERTIFICATE_PASSWORD ]] && need_cert=1
done

if [[ "$need_cert" == 1 ]]; then
    export_pass=$(openssl rand -base64 32)
    tmp_p12=$(mktemp -t apple-cert-XXXXXX).p12
    trap 'rm -f "$tmp_p12"' EXIT

    echo "Exporting Developer ID Application identity to temporary p12..."
    echo "(You may see a keychain access prompt -- click 'Always Allow'.)"
    security export \
        -k "$HOME/Library/Keychains/login.keychain-db" \
        -t identities \
        -f pkcs12 \
        -P "$export_pass" \
        -o "$tmp_p12"
    cert_b64=$(base64 < "$tmp_p12")
fi

# -- Push secrets --

for name in "${missing[@]}"; do
    case "$name" in
        APPLE_ID)                    val="$apple_id" ;;
        APPLE_TEAM_ID)               val="$team_id" ;;
        APPLE_APP_SPECIFIC_PASSWORD) val="$asp" ;;
        APPLE_CERTIFICATE)           val="$cert_b64" ;;
        APPLE_CERTIFICATE_PASSWORD)  val="$export_pass" ;;
    esac
    echo "  Setting $name..."
    printf '%s' "$val" | gh secret set "$name" --repo "$OWNER/$REPO"
done

echo
echo "Done. $OWNER/$REPO has ${#missing[@]} Apple signing secret(s) set."
```

---

## Secret Reference

Five secrets pushed to each macOS app's GitHub Actions:

| Secret | Source | Lifetime |
|--------|--------|----------|
| `APPLE_ID` | Keychain generic password | Permanent (your Apple ID email) |
| `APPLE_TEAM_ID` | Derived from cert at push time | Permanent (changes only if you join a different team) |
| `APPLE_APP_SPECIFIC_PASSWORD` | Keychain generic password | Until you revoke it or change your Apple ID password |
| `APPLE_CERTIFICATE` | Base64 of a fresh p12 export from keychain, with a random wrapper password | Until you rotate the cert |
| `APPLE_CERTIFICATE_PASSWORD` | Random `openssl rand -base64 32`, generated at push time | Paired with APPLE_CERTIFICATE; re-running push with --force issues a fresh pair |

The keychain service is `apple-developer-signing`. Two accounts are stored
there (`APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`). Everything else is
derived or generated fresh on each push.

The Developer ID Application certificate itself lives in the login
keychain's "My Certificates" section. It is never duplicated -- the push
script exports it to a temp file, base64-encodes it, pushes it, then
deletes the temp file.

---

## Rotation

**Rotate the cert** (annual expiry, or compromise):
  1. Import the new cert into Keychain Access
  2. Re-run `./scripts/push-apple-secrets.sh --force` on each repo
     (exports the new cert, generates a new random password, pushes both)

**Rotate the app-specific password** (revoked, or Apple ID password changed):
  1. Generate a new one at https://appleid.apple.com/account/manage
  2. Update keychain: `security add-generic-password -U -s apple-developer-signing -a APPLE_APP_SPECIFIC_PASSWORD -w "new-password-here"`
  3. Re-run `./scripts/push-apple-secrets.sh --force` on each repo

**Change Apple ID email**:
  1. Update keychain: `security add-generic-password -U -s apple-developer-signing -a APPLE_ID -w "new@email.com"`
  2. Re-run push with --force on each repo

---

## Known Quirks

**`security export -t identities` bundles all identities.** If you have
multiple Developer ID certificates in your login keychain (expired ones,
certs for different teams), they all get included in the p12. This is
harmless -- the release workflow's `codesign --sign "Developer ID Application"`
selects the right cert by CN prefix at sign time. The only effect is a
slightly larger APPLE_CERTIFICATE secret (maybe 6 KB vs 2 KB).

**First export triggers a keychain prompt.** The first time `security export`
touches a private key, macOS shows an access dialog. Click "Always Allow"
to authorize future exports without prompting. This is per-identity, so
if you import a new cert you'll see the prompt once more.

**`security add-generic-password -U` updates in place.** The `-U` flag
means "update if exists, create if not." This makes both the seed script
and manual rotation commands idempotent.
