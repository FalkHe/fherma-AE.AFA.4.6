# users

Owns the person record — who an account belongs to, independent of how they are
currently signed in. `auth` owns the credential/session lifecycle.

## Owns

- The `users` table: id, normalized username, password hash, `created_at`.

## Surface

- `service.create_user` / `get_user_by_username` / `get_user_by_id` /
  `verify_credentials` — called by `auth`.
- `GET /me` — requires `auth.CurrentAuth`.

## Notes

- `verify_credentials` also verifies against a fixed dummy hash on an unknown
  username, so timing can't be used to enumerate usernames (§5.4, `step-0.1.md`).
