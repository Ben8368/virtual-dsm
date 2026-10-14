# Web frontend maintenance

## Decision

Keep `web/js/script.js` in JavaScript for now. The repository contains one
approximately 630-line browser script and no package manifest, TypeScript
configuration or frontend build pipeline. The Dockerfile copies `web/` directly
into `/var/www/`; the browser consumes JavaScript from that directory.

The script displays startup status and download progress, receives WebSocket
messages, polls `msg.html` as a fallback, handles page visibility and redirects
to DSM. It does not implement DSM's own desktop or package UI. Most of this
repository's maintenance work is in Shell, Python and QEMU patches.

## Benefits and costs of TypeScript

TypeScript could check nullable DOM lookups, the active XMLHttpRequest, timer
handles and the progress result (`message`, `progress`, `size`). Those are useful
checks, but a full migration also needs a compiler dependency, a lockfile, build
configuration and CI integration. The Docker build would need to compile the
source or enforce that committed JavaScript matches it. Renaming the file to
`.ts` alone would break direct browser delivery.

Types alone would not validate WebSocket payloads, guarantee an anchor exists
in status HTML, or verify polling/reconnect/redirect timing. Runtime guards and
behavior tests address those risks directly.

## Next steps when changing the frontend

Prefer targeted JSDoc annotations and DOM/payload guards during future feature
work. JavaScript can later receive TypeScript checking with `allowJs`, `checkJs`
and `noEmit`, without changing the shipped asset. Such checking still requires
a pinned development dependency and a CI check; it is not enabled today.
See the [TypeScript `checkJs` documentation](https://www.typescriptlang.org/tsconfig/checkJs.html).

Revisit a full TypeScript migration if the status page grows into multiple
modules, structured API models, configuration forms or a management UI. Before
that migration, cover HTTP fallback, WebSocket reconnect, visibility changes,
portal redirects and progress parsing with meaningful regression tests.
