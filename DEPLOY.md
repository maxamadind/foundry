# Deploying Foundry to the public internet — $0

**Your part: 2 taps.** Everything else is already built and tested. Do this on
your iPhone.

---

## TAP 1 — Put Foundry online (Render, free forever, no card)

1. Open the **deploy link** your agent sends you. It looks like this:
   `render.com/deploy?repo=…` — one tap, pre-filled with everything.
2. Tap **Sign up** → continue with Google. Free plan. **No credit card asked.**
3. Render shows the pre-filled `foundry` service and asks for one value:
   **FOUNDRY_ADMIN_PASSCODE** — type a passcode you'll remember. This is the
   creator passcode: it locks *agent creation* on the public site so strangers
   with the URL can't spin up agents. Public chat pages stay open to everyone.
4. Tap **Deploy**. Wait about 5 minutes while it builds.

Done. Your public URL looks like `https://foundry-xxxx.onrender.com` — open it
on your phone. The demo agent ("Strength Basics") is already there and chatting,
which proves the whole pipeline works live.

**Good to know (honest, not hidden):**
- The free tier sleeps after ~15 minutes of no visitors; the first load after
  sleep takes 30–60 seconds. Normal.
- Anything you create on the public site (new agents, uploads) survives sleep
  but is **wiped if you ever tap Redeploy**. The demo agent is baked into the
  build, so the site always works after a redeploy — you'd just re-add your own
  agents through the creator page.

---

## TAP 2 — Take payments (Stripe Payment Links, $0, no code)

Do this whenever an agent should charge money. Each agent is free until you
decide otherwise.

1. Open your **Stripe Dashboard** app (or stripe.com) → tap **Payment links**
   in the sidebar → **Create payment link** → set the price and product name →
   **Create link** → **Copy link**.
2. Open your public Foundry site → tap **Create an agent** → enter your creator
   passcode → open your agent → expand **Add a payment link** → paste the
   Stripe link → **Save**.

A green **"Subscribe / pay"** button now appears on that agent's public page,
pointing at your Stripe checkout. Clear the field and save to remove it.

---

## Fallback host (only if Render ever fails)

- **Railway** (railway.app) — free trial credit, deploys from the same repo the
  same way. Check whether it asks for a card at signup; if it does, skip it.
- **Oracle Cloud Always Free** — a permanent $0/month virtual machine with a
  real disk (nothing gets wiped on redeploy). More setup, and signup requires
  a credit card for verification. Only worth it once Foundry is earning.

---

## Agent pre-step (not your tap — the agent does this)

Render deploys from a public GitHub repo. Before sending you the deploy link,
the agent pushes this folder (`~/workspace/foundry/`, already committed to git)
to a public repo and drops the one-tap `render.com/deploy?repo=…` link into
your chat. Nothing for you to do here.
