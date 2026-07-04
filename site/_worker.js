const statePattern = /^site_rev=(0|[1-9][0-9]*)(?:; manifest="\/[^"\\\r\n#]*")?$/;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2) + "\n", {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-cache",
    },
  });
}

async function increment(kv, key) {
  const current = Number.parseInt((await kv.get(key)) ?? "0", 10);
  await kv.put(key, String(Number.isFinite(current) ? current + 1 : 1));
}

function countValue(value) {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

async function observationStats(env) {
  const kv = env.PAGEDIGEST_OBSERVATIONS;
  if (kv === undefined) {
    return {
      configured: false,
      message: "Bind a KV namespace named PAGEDIGEST_OBSERVATIONS to enable the live counter.",
    };
  }
  const [manifestRequests, statePresent, stateValid, stateInvalid] = await Promise.all([
    kv.get("manifest_requests"),
    kv.get("state_present"),
    kv.get("state_valid"),
    kv.get("state_invalid"),
  ]);
  return {
    configured: true,
    manifestRequests: countValue(manifestRequests),
    statePresent: countValue(statePresent),
    stateValid: countValue(stateValid),
    stateInvalid: countValue(stateInvalid),
  };
}

function recordObservation(request, env, ctx) {
  const url = new URL(request.url);
  const rawState = request.headers.get("PageDigest-State");
  const match = rawState === null ? null : statePattern.exec(rawState);
  const facts = {
    event: "pagedigest_request",
    path: url.pathname,
    manifestRequest: url.pathname === "/.well-known/pagedigest.json",
    statePresent: rawState !== null,
    stateValid: match !== null,
    observedSiteRev: match === null ? null : Number(match[1]),
    userAgent: request.headers.get("user-agent"),
  };
  console.log(JSON.stringify(facts));

  const kv = env.PAGEDIGEST_OBSERVATIONS;
  if (kv === undefined) {
    return;
  }
  const writes = [];
  if (facts.manifestRequest) {
    writes.push(increment(kv, "manifest_requests"));
  }
  if (facts.statePresent) {
    writes.push(increment(kv, "state_present"));
    writes.push(increment(kv, facts.stateValid ? "state_valid" : "state_invalid"));
  }
  if (writes.length === 0) {
    return;
  }
  const work = Promise.all(writes).catch((error) => {
    console.error(
      JSON.stringify({
        event: "pagedigest_observation_write_error",
        message: error instanceof Error ? error.message : String(error),
      }),
    );
  });
  if (ctx?.waitUntil) {
    ctx.waitUntil(work);
    return;
  }
  void work;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    recordObservation(request, env, ctx);

    if (url.pathname === "/__pagedigest/cooperation.json") {
      return jsonResponse(await observationStats(env));
    }

    return env.ASSETS.fetch(request);
  },
};
