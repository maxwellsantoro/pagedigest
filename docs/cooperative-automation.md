# Cooperative automation: observable client behavior

`PageDigest-State` makes a consumer's manifest observation visible in ordinary
request logs. It is a corroborating signal, not an identity or authentication
scheme. The syntax and version 1 reservation live in
[SPEC.md §5.4](../SPEC.md#54-optional-cooperation-request-header).

## Classification model

Publishers should classify behavior over a time window, not grant trust from
one header:

| Observed pattern | Interpretation | Suggested treatment |
|---|---|---|
| Manifest fetch, changed-URL fetches, matching state | Cooperative | Higher limits; lower bot suspicion |
| Page fetches with no manifest access | Non-cooperative or unaware | Normal or tighter bot policy |
| Impossible future or persistently stale state | Broken client or probing | Ignore the signal; investigate or downgrade |
| Matching state plus unchanged covered-page overfetch | Non-compliant | Rate-limit with logged evidence |
| Header with no corroborating manifest fetch | Weak signal | Ignore until corroborated |

The useful metric is the unchanged-page overfetch ratio:

```text
unchanged covered page requests / all covered page requests
```

Compute it for a stable client identity and time window appropriate to the
publisher. IP address alone is a noisy identity because NAT, proxies, and
address rotation can merge or split clients. Prefer an authenticated account,
declared crawler identity with verification, mTLS identity, or another signal
the publisher already trusts; otherwise keep the classification conservative.

## nginx: log first, enforce from evidence

This configuration extracts only the strict reserved syntax and writes it into
a JSON access log. It deliberately does not rate-limit merely because a header
is absent.

```nginx
map $http_pagedigest_state $pagedigest_site_rev {
    default "";
    ~^site_rev=(0|[1-9][0-9]*)(?:;\ manifest="/[^"]+")?$ $1;
}

log_format pagedigest escape=json
  '{"time":"$time_iso8601",'
  '"remote_addr":"$remote_addr",'
  '"request_id":"$request_id",'
  '"method":"$request_method",'
  '"uri":"$request_uri",'
  '"status":$status,'
  '"pagedigest_site_rev":"$pagedigest_site_rev",'
  '"user_agent":"$http_user_agent"}';

access_log /var/log/nginx/pagedigest.json pagedigest;
```

An aggregation job joins manifest access, the revision visible at that time,
and subsequent covered-page requests. Export only sustained classifications
to an nginx `map`, allowlist, or rate-limit tier. Keep a neutral default and a
short expiry so clients can recover after fixing their behavior.

## Cloudflare Worker and bot-management sketch

Cloudflare recommends using service bindings for platform storage and
structured Workers logs for production observability. A Worker can record the
request-local facts without buffering response bodies:

```js
const statePattern = /^site_rev=(0|[1-9][0-9]*)(?:; manifest="\/[^"]+")?$/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const rawState = request.headers.get("PageDigest-State");
    const match = rawState === null ? null : statePattern.exec(rawState);

    console.log(JSON.stringify({
      event: "pagedigest_request",
      path: url.pathname,
      manifestRequest: url.pathname === "/.well-known/pagedigest.json",
      statePresent: rawState !== null,
      stateValid: match !== null,
      observedSiteRev: match === null ? null : Number(match[1]),
      botScore: request.cf?.botManagement?.score ?? null,
    }));

    return env.ORIGIN.fetch(request);
  },
};
```

Request-time WAF or Bot Management rules can distinguish a missing, malformed,
or syntactically valid header, but they cannot infer prior manifest access from
that request alone. Correlate Workers Logs or Analytics Engine data first, then
feed sustained classifications into a short-lived Cloudflare managed list or
rate-limiting tier:

1. Keep verified cooperative clients on the normal or higher-limit path.
2. Leave unknown clients on the baseline policy.
3. Apply a tighter rule only to clients with repeated unchanged-page overfetch
   or impossible state, and retain the evidence window that caused it.
4. Expire classifications so repaired clients return to neutral and can earn
   cooperative treatment.

Do not put Cloudflare API credentials in Worker source or call the Cloudflare
REST API from the request path. Use bindings and an out-of-band control job.
See Cloudflare's current [Workers best
practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
and [Bot Management documentation](https://developers.cloudflare.com/bots/).

## pagedigest.org dogfood observer

The pagedigest.org static site ships a Cloudflare Pages advanced-mode Worker at
`site/_worker.js`. It follows Cloudflare's Pages Functions pattern: handle the
protocol-observer endpoint, then fall through to static assets with
`env.ASSETS.fetch(request)`.

It always writes structured request logs for:

- manifest requests
- whether `PageDigest-State` was present
- whether the header matched the reserved v1 syntax
- the observed `site_rev` when valid

It exposes a small same-origin JSON endpoint:

```text
/__pagedigest/cooperation.json
```

Without storage configured, the endpoint reports `configured: false` and the
site remains fully static. To persist the tiny counter, create a Cloudflare KV
namespace and bind it to the Pages project as `PAGEDIGEST_OBSERVATIONS`.

Example setup:

```bash
npx wrangler kv namespace create PAGEDIGEST_OBSERVATIONS
```

Then add the returned namespace as a Pages KV binding named
`PAGEDIGEST_OBSERVATIONS` in the Cloudflare dashboard or project configuration.
After deployment, the homepage will surface valid `PageDigest-State` observations
and manifest request counts from that endpoint.

The counter is intentionally approximate. KV read-modify-write increments can
lose concurrent updates; that is acceptable for a public proof widget. Treat
Workers logs or Analytics Engine as the evidence source for real enforcement.

## Spoofing and limits

A client can copy a state value. That is why the header alone earns nothing.
A plausible value plus manifest access plus low unchanged-page overfetch is the
behavior the publisher wanted in the first place; intent is irrelevant. A
client that copies the value and still hammers unchanged pages supplies the
publisher with direct counter-evidence.

Do not use `PageDigest-State` to authorize content, bypass authentication,
identify a legal entity, or make irreversible blocking decisions.
