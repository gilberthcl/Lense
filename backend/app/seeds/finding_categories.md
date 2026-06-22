# FINDING CATEGORIZATION STRUCTURE

## Goal / Purpose
Provide a succinct conclusion to hunt findings that gives the client a clear next
step, and standardize the terminology used among hunters in reporting. Each
finding is assigned exactly ONE outcome category from the canonical list below.
Categories are bilingual — use the label matching the hunt's report language.

## Example use case
| Field | Value |
|---|---|
| Outcome | Potential Policy Violation Identified |
| Severity | Medium–Low |
| Timeframe | Feb 2, 2022 – Mar 28, 2022 |
| Hosts affected | NY-01-L-12o847, NY-01-L-167243 |
| Recommendation | Determine if YandexDisk is approved by the organization, and whether security controls are appropriately allocated to all instances. If not, remediate and engage DLP measures to control organizational documents within YandexDisk. |

## Canonical outcome categories (use exact terminology)

1. **Malicious Activity Identified** — *Actividad Maliciosa Identificada*
   When used: you found bad.
   Examples: ransomware artifacts, active netconns to known-bad.

2. **Suspicious Activity Identified** — *Actividad Sospechosa Identificada*
   When used: oddness found, or bad with low confidence.
   Examples: netconns tied to low-fidelity IOCs; registry changes for keylogging with no exfil.

3. **Risky Behavior Identified** — *Comportamiento de Riesgo Identificado*
   When used: activity/behaviors that could lead to exploitation but are not inherently suspicious.
   Examples: credentials stored in cleartext or publicly available.

4. **Potential Policy Violation Identified** — *Posible Violación de Políticas Identificada*
   When used: findings that potentially violate acceptable use / organizational policy.
   Examples: non-business software (Steam, TorBrowser) run on 20 machines.

5. **Vulnerable Configuration Identified** — *Configuración Vulnerable Identificada*
   When used: a protocol, aspect of a protocol, or configuration option that requires changing/disabling.
   Examples: NTP servers pointing to inappropriate locations; obsolete protocols (POP, SMBv1) enabled; a CVE-202X-XXXX identified, or outdated software versions running.

6. **New Hunting Opportunity Identified** — *Nueva Oportunidad de 'Hunt' Identificada*
   When used: a new hunt is identified.
   Examples: you find a new hunting opportunity.

7. **Unconfirmed Activity Identified** — *Actividad No Confirmada Identificada*
   When used: observed activity that can relate to IOAs and requires client follow-up / confirmation to be acceptable.
   Examples: local admin account created.

8. **Potential Baseline Activity Identified** *(optional, for initial hunts)* — *Posible Actividad "Baseline" Identificada (opcional, para investigaciones iniciales)*
   When used: RMMs / remote-access tooling not yet confirmed acceptable by the client.
   Examples: installing remote-access software previously unseen in the environment; add an explanation to the summary.

> Note: "Informational" is a **severity** level (High / Medium / Low / Informational),
> not an outcome category. Findings that are merely informational should carry the
> closest applicable outcome above (commonly *Unconfirmed Activity Identified*).
