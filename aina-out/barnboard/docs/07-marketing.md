# Barnboard — Marketing Pack

*Stage 7 of the AiNa App Factory pipeline · engine: local Claude*

## Brand strategy

- **Positioning:** the anti-enterprise farm tool. Not "AgTech platform" — a
  sturdy, self-hosted daily companion. Deliberately boring technology, loudly
  farmer-owned data.
- **One-line promise:** *Retire the pocket notebook.*
- **Audience:** owner-operators of 30–150-cow dairy farms; reached through
  farming Facebook groups, county co-op newsletters, and word of mouth — not ads.
- **Tone:** plain, concrete, slightly wry. Numbers over adjectives ("one saved
  tanker pays for years of hosting"). Never talk down to farmers.
- **Visual identity:** pasture green (#15803d family) + cream/stone neutrals +
  amber CTA; Inter typeface; the 🐄 mark. Matches the app's own accent so the
  landing page and product feel like one thing.

## Key messages (in priority order)

1. **Safety:** milk from a treated cow never reaches the tank by accident —
   the DO-NOT-TANK alert is the hero feature in all copy.
2. **Speed:** logging a cow is one tap + one number; faster than the notebook.
3. **Ownership:** self-hosted, one SQLite file, CSV export of everything —
   "your data is yours" is a differentiator against subscription AgTech.
4. **Zero-infrastructure reminders:** the iCal feed puts deadlines in the
   calendar app the farmer already checks.

## Deliverable

`app/marketing.html` — a self-contained landing page (Tailwind CDN + Google
Fonts only): sticky nav, hero with 3 benefit bullets and amber CTA, 8 feature
cards mapped 1:1 to shipped P0 features, 4-question FAQ as no-JS accordions,
3 copy-paste social posts (X, Facebook farming groups, LinkedIn), footer.
Mobile-first; reflows cleanly at 375 px.

## FAQ themes covered

Barn connectivity · data ownership/backup · why withholding days are
user-entered (regulatory honesty) · the no-login deployment posture.

## Not claimed anywhere (honesty guardrails)

No "AI-powered", no "trusted by N farms" fabricated social proof, no pricing
(it's free/self-hosted), no promises about drug-rule databases or hardware
integration the product doesn't have.
