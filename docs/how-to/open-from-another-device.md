# Open the studio from another device

The studio binds `127.0.0.1`, so only this machine can open it. To open it from a phone or
another computer on your tailnet, put Tailscale serve in front of it.

1. Start the studio on its usual address, and name the page's HTTPS origin:

   ```sh
   uv run studio --allow-origin https://my-mac.example.ts.net:8765
   ```

2. Let Tailscale serve that port over HTTPS:

   ```sh
   tailscale serve --bg --https=8765 http://127.0.0.1:8765
   ```

3. Open **https://my-mac.example.ts.net:8765** on the other device.

Use the machine name that `tailscale status` shows. The startup line names the origins that
may post, so you can compare it with the address bar.

Do not use `tailscale funnel` for the studio. Funnel puts the page on the public internet,
and the studio has no login.

## Why the flag is necessary

The server checks the Host header on every request. It also checks the page's Origin on writes.
Explicit allowed origins identify trusted proxy hosts. Behind the proxy, the page's origin is
`https://my-mac.example.ts.net:8765`, and the server bound `127.0.0.1`. So the server refuses
every POST until you name that origin. A page on another site cannot send that origin.

The flag takes `scheme://host[:port]` only. The studio refuses `null`, `*`, a path, or a
value with no scheme, and does not start. `null` would let a sandboxed frame on any site post.

## Plain HTTP on a local network

Use `--host 0.0.0.0` to bind local interfaces.
Add `--allow-origin http://my-mac.example.ts.net:8765` when you use that hostname.
A browser does
not treat that address as a secure context, because it is neither HTTPS nor `localhost`.
The page creates its browser identities with `crypto.getRandomValues` when `crypto.randomUUID` is unavailable.
The workspace picker, size controls, references, and generation work over plain HTTP.
Microphone recording and screen wake locks still require HTTPS or `localhost`.
