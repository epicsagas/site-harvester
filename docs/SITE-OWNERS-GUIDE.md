# Site Owner's Guide: Responding to Crawlers and Harvesters

> Audience: companies and operators whose content may be collected by open-source tools
> like site-harvester. This document is written from the perspective of the **site being
> harvested**, not the user doing the harvesting.

## 1. Understanding the Situation

Open-source harvesters like site-harvester collect content into a personal archive, at
human reading speed, within the access rights of an existing paid subscription. There is
deliberately no CAPTCHA solving, anti-bot evasion, or paywall bypass. So what you are
facing is not an "intrusion" — it is **a legitimate subscriber's personal backup**.

Two concerns remain real, though:

- **Server load** — large initial sweeps (full-archive collection) can strain infrastructure
- **Content distribution control** — collected text may be redistributed (this is a user
  violation, not a tool capability; the tool's own terms forbid it)

## 2. Traditional Defense: Defense-in-Depth

If your business requires a baseline defense:

| Layer | Means | Effect |
|-------|-------|--------|
| Legal / policy | Terms of Service prohibiting scraping without prior written consent; robots.txt expressing refusal of automated bots | Legal grounds, demonstration of good faith |
| Architecture | Design core data around APIs (SSR/JSON API); obfuscate CSS class names | Defeats parsing logic — limited effect against harvesters that use the API directly |
| Infrastructure | WAF / anti-bot solutions blocking abnormal traffic; rate limiting | Protects against server load |

**Reality check**: collection by a paying subscriber through their own account is
technically hard to distinguish from normal traffic. API obfuscation and bot
fingerprinting offer poor cost-effectiveness and can degrade the legitimate user
experience.

## 3. Paradigm Shift: Building a Moat Through "Gap" and "Openness"

If your content quality and editorial moat are overwhelming, opening up can beat locking down.

| | Defense-first (Closed) | Moat-first (Open & Hybrid) |
|---|------------------------|----------------------------|
| Data access | Strict blocking and hiding | Keep content public, strengthen original branding |
| Marketing effect | Limited inbound | Natural virality and distribution through crawling and reposting |
| Server management | Try to block every bot | Minimally control only abnormal load |

With the advance of AI and crawlers, text (raw data) has become a commodity anyone can
replicate. What cannot be replicated:

- **Taste** — the curation ability to decide what to keep and what to discard amid the noise
- **Predictability** — brand trust that provides direction amid an uncertain market
- **Ecosystem and membership** — a living original community, continuously updated
  relationships, access to the original author

What gets scraped away is yesterday's "text fragment (the shell)" — these are not.

## 4. Practical Checklist

1. **Minimal server protection**: rate limiting plus a WAF targeting abnormal traffic only.
   Don't try to block collection at legitimate subscriber speed.
2. **Tidy up robots.txt and ToS**: state your position on automated collection explicitly.
   Make no-redistribution clauses unambiguous.
3. **Strengthen original branding**: imprint source, author, and brand on the content
   (watermarks, style, the structure itself as signature).
4. **Design for renewal value**: an archived snapshot dies over time. Build reasons to
   keep coming back — updates, interaction, community.
5. **Separate membership tiers**: open the text, but keep curation, prediction, and access
   in the paid layer.

## 5. Conclusion

Free yourself from the stress of unnecessary crawl blocking. Put in place only the minimal
anti-bot apparatus needed to protect your infrastructure, then focus on product quality and
membership value — that is the strongest and most sustainable gap strategy.
