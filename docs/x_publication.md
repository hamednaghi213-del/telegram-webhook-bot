# X Publication

X is an explicit Workspace destination: only prepared content with
`routing_platforms=("x",)` (or an explicit set including X) reaches it.
Ordinary Telegram/Bale and Legacy routing is unchanged. Existing destination
verification, membership, administrative controls and translation apply.

The adapter consumes the existing full Telegram text/entity plan, including the
caption for media posts, preserves visible quote content and expands hidden HTTP
links, and removes HTML styling. It sends one post, without silent truncation,
attachment dropping or automatic thread splitting. X enforces account-specific
text and video duration entitlements; rejected content is returned as a failed
delivery for editing/retry.

## Credentials and media

The existing X OAuth token getter and refresh implementation are reused without
changes. Connections need `tweet.write`; media also needs `media.write`.
If the configured OAuth scopes or existing grant lack media.write, configure that
scope through the existing X_OAUTH_SCOPES setting and reconnect using the existing
Workspace action. A 401 triggers one refresh; another 401 marks reconnect required.
403 and rate limiting do not invalidate the connection. Tokens and HTTP response
bodies are not included in errors.

Supported attachments: up to four JPEG/PNG/WebP photos, or one GIF/MP4.
Image and GIF limits are 5 MiB and 15 MiB; the adapter caps video at 512 MiB.
Telegram/Bale file references use their respective existing download adapters.
Unsupported attachments and mixed video/GIF albums fail before creating a post.
Media uses v2 initialize/append/finalize and bounded processing-status polling.
Uploads may be repeated after a safe failure; unfinished uploads never become
published posts. The original caption is kept for finalized editorial media.

## Delivery and retry

The shared engine persists the real post ID as the primary message ID and indexes
it with the immutable X account ID. DeliveryResult.message_url returns
https://x.com/i/status/{post_id}, including on idempotent retries.
No Telegram/Bale edit/delete pairing is added for X.

A unique `x-send-intent` part is written before create-post. With persistent state
enabled, it uses the existing publication_delivery_parts unique constraint;
no schema migration is required. Database write failure stops the send.
A definite rejection releases the marker, permitting the shared engine's bounded
retry. Short rate-limit waits are retried with bounded backoff; longer waits return
x_rate_limited. Media transient failures are also bounded.

Timeouts, create-post 5xx, malformed success responses and crashes after arming
leave the intent marker in place. A worker restart cannot blindly repost when
success persistence is missing. Operators must inspect the destination account:
record the confirmed post ID through the existing success persistence path, or
remove only the matching intent after confirming no post exists. Never clear a
marker while the original worker may still be sending.

Restart protection requires ENABLE_PERSISTENT_PUBLICATION_STATE=true and the
existing service-role database configuration. In-memory mode protects only the
current process. X does not provide a transactional exactly-once guarantee;
ambiguous deliveries deliberately require reconciliation.

## API references

- https://docs.x.com/x-api/posts/create-post
- https://docs.x.com/x-api/media/quickstart/media-upload-chunked
- https://docs.x.com/x-api/media/upload-media

Unit tests mock transport and storage; they do not publish to a real X account.
