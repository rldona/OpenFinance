# ADR-0008: AGPL-3.0 as the distribution license

- Status: Accepted
- Date: 2026-10-31 (proposed) · 2026-11-01 (accepted, OF-504)

## Context

We want OpenFinance's improvements to remain open, also when someone offers it as a network service.

Before accepting it, four things were pending: auditing the dependencies' licenses, choosing the contribution policy (DCO or CLA), assessing the implications for commercial services and extensions, and deciding on the license text and SPDX headers.

## Decision

1. **License: AGPL-3.0-or-later.** The verbatim text of the GNU Affero General Public License v3, downloaded from <https://www.gnu.org/licenses/agpl-3.0.txt>, is in [`LICENSE`](../../LICENSE). The metadata declares it with its SPDX identifier: `license = "AGPL-3.0-or-later"` in `services/api/pyproject.toml` and `"license": "AGPL-3.0-or-later"` in `apps/web/package.json`.
2. **Compatible dependencies.** The OF-504 audit ([docs/legal/dependencias.md](../legal/dependencias.md)) found no incompatible license. There are only permissive licenses and psycopg (LGPL-3.0-only, compatible with the GPLv3 family). CI checks on every change that production dependencies stay within that list (`make licenses CHECK=1`).
3. **Contributions with DCO, no CLA.** Each commit carries `Signed-off-by:` (`git commit -s`) and with it the contributor certifies the [Developer Certificate of Origin 1.1](https://developercertificate.org/). No one is asked to assign rights or sign a CLA: each contribution enters under the same AGPL-3.0-or-later. Details in [CONTRIBUTING.md](../../CONTRIBUTING.md).
4. **No per-file SPDX headers.** The license is declared once, in `LICENSE` and in the package metadata. This holds for the whole repository unless a file says otherwise.

## Consequences

- Strong copyleft: anyone who modifies OpenFinance and offers it over a network must offer the source code of their changes to its users (AGPL-3.0 §13).
- A household that installs it at home without modifying it has no additional obligation.
- Commercial use is allowed under the same terms. It may reduce adoption by companies that avoid the AGPL.
- Without a CLA, the project cannot relicense or offer commercial licenses without each author's permission. This is a conscious decision: nobody concentrates rights that the rest do not have.
- "or-later" allows using the code under future versions of the AGPL published by the FSF.
- Third-party extensions (ADR-0006, deferred) will be decided when there is an SDK. In the meantime, a module integrated into the API process or the web bundle is part of the work and falls under the AGPL.
- If Docker images are published in the future, the source code of the GPL components of their base system must also be offered (see the audit).
