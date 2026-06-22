Goal/Purpose
To provide a succinct conclusion to hunt findings that provides a clear next step for the client, and to standardize the terminology used among hunters in reporting. 
Example Use case: 

[TABLE]
Outcome | Organizational Policy Requested [Our word bank below]
Severity | MED-LOW
Timeframe | Feb 2,2022 – Mar 28, 2022
Hosts affected | NY-01-L-12o847 
NY-01-L-167243
Recommendations | Determine if YandexDisk is approved by the organization, and if security controls are appropriately allocated with all instances of YandexDisk. If not, remediate and engage in DLP measures to control organizational documents within YandexDisk.
[/TABLE]

Outcome Wordbank

[TABLE]
Outcome / Identified | When Used | Example(s)
Malicious Activity Identified

Actividad Maliciosa Identificada | You found bad | Bluecrab, Ransomware artifacts, active netconns to knownbad.
Suspicious Activity Identified

Actividad Sospechosa Identificada | Oddness found or bad with low confidence | Netconns tied to low-fidelity IOCs, registry changes to keylogging with no exfil.
Risky Behavior Identified

Comportamiento de riesgo identificado | Activity or behaviors that could lead to exploitation, but are not inherently suspicious | Stored credentials in cleartext or are publicly available
Potential Policy Violation Identified

Posible Violación de Políticas Identificada | Findings that potentially violate acceptable use, organizational policy. | Non-business software (Steam, TorBrowser) run on 20 machines.
Vulnerable Configuration Identified

Configuración Vulnerable Identificada | You identified a protocol, aspects of a protocol or a configuration option within a tool that requires changing/disabling. | NTP servers pointing to inappropriate locations, obsolete protocols (POP, SMBv1) enabled within the environment. CVE-202X-XXXX is identified, or older software versions running
New Hunting Opportunity Identified

Nueva Oportunidad de ‘Hunt’ Identificada | A new hunt is identified | You find a new hunting opportunity
Unconfirmed Activity Identified

Actividad No Confirmada Identificada | Activity that is observed that can relate to IOAs, requires client follow up/confirmed to be acceptable | Local Admin account created
Potential Baseline Activity (Optional, to be used in initial set of Hunts)

Posible Actividad “Baseline” Identificada (opcional, para usar en investigaciones iniciales) | When finding RMM’s that are not confirmed by client as acceptable within environment | Installing remote access software, where previously unseen in environment; add to summary (explanation)
[/TABLE]

