# Internal application design system

The final stylesheet is `frontend/src/styles/workspace-design.css`, imported after the legacy base stylesheet in `main.tsx`. Components use the existing React/CSS system. The installed project does not use Tailwind; no second styling framework was added.

## Foundations

| Token | Light value | Purpose |
| --- | --- | --- |
| `--bg` | `#F1F2EC` | Canvas |
| `--surface` | `#FFFFFF` | Cards and topbar |
| `--surface-raised` | `#F8F9F5` | Controls and secondary surfaces |
| `--text-h` | `#151915` | Headings and important values |
| `--text` | `#414B41` | Body text |
| `--text-muted` | `#626E62` | Readable secondary labels |
| `--brand-lime` | `#C8FD39` | Primary actions and metric emphasis |
| `--accent-bg` | `#E6F8CC` | Soft accent backgrounds |
| `--border` | `#DCE1D7` | Visible surface boundaries |

The sidebar uses charcoal `#1F2432` and lime active navigation. Dark analytical cards use `#101312`. Muted text and borders are slightly stronger than the directive's fallback values for readability. Dark mode and sage accent remain supported preferences; light is the default. Settings also preserve compact density and reduced motion.

## Composition

- One shared 260px desktop sidebar, grouped into six navigation sections, with mobile drawer and collapse behavior. The mobile main-margin reset matches desktop selector specificity.
- White topbar with breadcrumb, command palette and native keyboard-operable account disclosure. Escape closes the disclosure; profile and settings are real destinations.
- Page headings scale 28–40px, with restrained letter spacing, uppercase context labels, 18–20px card radii and 20–24px layout gaps.
- Visualizations uses a 12-column grid: dark feature spans eight, lime metrics four; relationships receive a larger area. It collapses at 1100px and 480px.
- Memory and Studio use a configuration inspector beside a results canvas. Forecasting has model controls beside the plot. These become single columns by 900px.
- Tables scroll within their panel. Charts retain underlying value tables and source-unit labels. No arbitrary currency, growth or analytical values are invented.
- Existing chart reveal and sidebar transitions are restrained; reduced-motion preferences suppress animation. Authentication's separate three-stage animation is preserved.

## Reference limitation

The Figma context and screenshot tools returned the Starter-plan usage limit for the supplied references. The recording and third reference screenshot were unavailable in the attachment. This implementation follows the written fallback and existing integrated design work; exact frame fidelity is **not verified**. After manual sign-in, all 13 protected routes were captured at the six requested widths. Desktop inspection and key mobile views confirmed the design; remaining inherited contrast and layout conflicts found in that review were corrected.
