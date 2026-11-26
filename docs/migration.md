# Migration notes

## Verification dry-run

For `verify --dry-run`, the terminal summary now says `already verified` where it used to say
`up to date`. Update JSON consumers of this mode to read `summary.already_verified` in place of
`summary.skipped`. The count represents ZIPs skipped because they have current verification
markers.
