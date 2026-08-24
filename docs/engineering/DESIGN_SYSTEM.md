# Website design system

The canonical site is maintained in the private `agentdiff-web` repository and deploys at `https://kam6l.github.io/agentdiff-web/`.

## Visual language

- Warm editorial canvas, near-black text, quiet neutral rules, white artifact surfaces, restrained green for verified states, and amber/red only for attention or refusal.
- One legible sans-serif stack for prose and one system monospace stack for commands, identities, and evidence.
- Square or subtly rounded geometry. Avoid oversized pills, glassmorphism, neon gradients, floating glow, and generic “AI” ornament.
- Alternate dense proof surfaces with generous reading space. Real product artifacts should carry more visual weight than decorative illustration.
- Use the AgentDiff mark and local, attributed brand SVGs. Brand marks identify compatible workers, not partnerships.

The implementation tokens and responsive rules live in `agentdiff-web/src/styles.css`. Reuse existing components before adding variants.

## Content rules

- Lead with the concrete promise and explain why generation is not proof.
- Separate `Available`, `Foundation`, and `Roadmap` visually and verbally.
- Every metric, digest, certificate, before/after patch, and screenshot must trace to a committed fixture or captured run. Label rejected and simulated artifacts accurately.
- Prefer “container boundary” to “perfect sandbox,” “integrity hash” to “signature,” and `NOT_PROVEN` to vague failure language.
- Do not imply vendor endorsement from logos.

## Interaction and accessibility

- Semantic landmarks, visible keyboard focus, a focus-only skip link, labeled icon buttons, dialog escape handling, and reduced-motion support are required.
- The installation command is a real button with stable-width copied feedback.
- Documentation must support persistent desktop navigation, a mobile drawer, search, previous/next navigation, and per-page status.
- Verify 375, 430, 768, 1024, 1440, and 1920 pixel widths with no horizontal overflow. Test deep-route refresh under the `/agentdiff-web/` base path.

## Assets and metadata

Keep public assets under `agentdiff-web/public/`; never depend on a runtime CDN for core visuals. Every indexable route receives a specific title, description, canonical URL, Open Graph metadata, and sitemap entry during `pnpm run build`. The Pages build must keep `.nojekyll` and `404.html`.
