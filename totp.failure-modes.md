# totp failure modes

`totp` keeps one authenticator secret per account in a mode 600 env file and
prints the current code, usually six digits. An agent needs this when a network turns on
two-step verification and the agent must sign in again later.

```text
totp save ENVFILE PREFIX   read an otpauth:// URI on stdin, store it
totp code ENVFILE PREFIX   print the current code
```

`PREFIX` names the account, for example `AWIN`. It uses capital letters,
digits and underscores. The keys are `PREFIX_TOTP_SECRET`, `_ALGO`, `_DIGITS`
and `_PERIOD`. Other lines in the file stay as they are.

Each row below has a case in `totp.test.sh`, unless the last column says
`not tested`.

| # | Failure | What `totp` does | Exit | Tested |
|---|---------|------------------|------|--------|
| 1 | The URI is a counter (`otpauth://hotp/`) or not `otpauth://` at all | Refuses. A counter code cannot be derived from a clock. | 2 | yes |
| 2 | The URI has no `secret` | Refuses. | 2 | yes |
| 3 | The secret is not valid base32 | Refuses on `save` and on `code`. | 2 | yes |
| 4 | The algorithm is not SHA1, SHA256 or SHA512 | Refuses. | 2 | yes |
| 5 | Digits are not 6 to 8, or the period is not a positive number | Refuses. | 2 | yes |
| 6 | `PREFIX` has other characters than capitals, digits and underscores | Refuses. A free-form prefix could match or rewrite another key. | 2 | yes |
| 7 | The env file can be read by group or others | `code` refuses. `save` sets mode 600 on every write. | 3 | yes |
| 8 | The env file is missing, or has no key for `PREFIX` | Refuses and names the file or the missing key, never a value. | 4 | yes |
| 9 | `save` runs twice for one prefix | Replaces the four keys. It does not add a second set. | 0 | yes |
| 10 | The secret leaks to the terminal or into an error | Output holds only the prefix, digits, period and algorithm. A test searches all output for the secret. | 0 | yes |
| 11 | The output code is wrong against a known answer | Checked against the RFC 6238 vectors for SHA1, SHA256 and SHA512 at fixed times. | 0 | yes |
| 12 | The host clock is more than about 30 seconds off | The service rejects the code. `totp` cannot see this. Run `date -u` and compare with a network clock before blaming the secret. | 0 | not tested |
| 13 | Digits or period hold a non-ASCII digit such as `²` | Refuses with the same message as any bad number. It must not crash. | 2 | yes |
| 14 | Many `save` calls run at the same time | A directory lock makes them take turns. No prefix loses its keys. | 0 | yes |
| 15 | The env file is a symlink | `save` writes through the link. The link stays a link and the target holds the new keys. | 0 | yes |
| 16 | The directory cannot be written | Refuses and leaves no temp file behind. A stale temp name cannot block the next save. | 5 | yes |
| 17 | The env file exists with a loose mode when `save` runs | `save` sets mode 600 on the result. | 0 | yes |

`TOTP_NOW` sets the time in seconds. It exists for the tests. Do not set it in
real use.

The secret is the whole account: anyone who holds it can sign in. Keep the env
file out of Git and out of chat. Keep the service's recovery code in the same
file under its own key.
