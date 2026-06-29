# Security

lazarus executes **whitelisted** commands over SSH to remediate failures. Treat
it as software with real reach into your hosts and run it accordingly.

## Operating safely

- **Least-privilege SSH.** Give lazarus a dedicated key that can run only the
  remediation commands you configure — not a full-access admin key.
- **Whitelist only.** lazarus runs only the `action` strings under each host's
  `remediation`. Review them; they execute verbatim on the target.
- **Audit with `--dry-run`** before enabling real remediation, to confirm what
  would run.
- **Keep secrets out of config.** The webhook URL is read from an environment
  variable (`${DISCORD_WEBHOOK_URL}`). Never commit real webhook URLs or keys.
- The `max_attempts` and `cooldown_seconds` limits exist to prevent runaway
  remediation; do not set them so high that a flapping host causes a command
  storm.

## Reporting a vulnerability

Please report security issues privately to the maintainer rather than opening a
public issue. Include reproduction steps and the affected version.
