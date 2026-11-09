# Daily monitor flow

Working diagram for the architecture in `Project Architect/architecture.md`. Not a TVFI deliverable.

The cream box is our system. The blue box is TVFI's system. The green box is the later dashboard prototype. Arrows enter those boxes from the side, under the titles. The saved picture is `data-flow.png`.

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","fontFamily":"arial","fontSize":"15px","lineColor":"#1e293b","textColor":"#0f172a"},"flowchart":{"nodeSpacing":36,"rankSpacing":40,"padding":18,"htmlLabels":true,"curve":"linear"}}}%%
flowchart LR
  subgraph ours["our system"]
    direction TB
    RF["Daily risk-free curve"]
    FP["Monthly Fiera premium"]
    IN["Intake"]
    RFS["Risk-free snapshot"]
    POL["Premium record"]
    PAR["Static insurer parameters"]
    CB["Curve builder"]
    IMP["Implied curve workbook"]
    BASE["Baseline curve"]
    REC["Construction record"]
    TR["Trigger"]
    DEC["Decision log"]
    RF --> IN
    FP --> IN
    IN --> RFS
    IN --> POL
    RFS --> CB
    POL --> CB
    PAR --> CB
    CB --> IMP
    CB --> REC
    REC --> TR
    BASE --> TR
    TR --> DEC
  end

  subgraph tvfi["TVFI's system"]
    direction LR
    RC["run_curves.py"]
    SLOPE["Slope"]
    AR["analyse_results.py"]
    PROF["Profitability workbook"]
    RC --> SLOPE
    SLOPE --> AR
    AR --> PROF
  end

  subgraph later["later prototype"]
    direction LR
    SNAP["monitor_snapshot.json"]
    W["Cloudflare Worker"]
    SNAP --> W
  end

  IMP --> RC
  BASE --> RC
  DEC --> SNAP
  PROF --> SNAP

  style ours fill:#fffbeb,stroke:#a16207,color:#0f172a
  style tvfi fill:#eef2ff,stroke:#3730a3,color:#0f172a
  style later fill:#ecfdf5,stroke:#047857,color:#0f172a
```
