# Finzoria

**Global student finance. Brighter futures.**

Finzoria is a cross-border finance planner for international students.
Manage budgets, tuition bills, currencies and family contributions
through a unified dashboard, with an optional AI assistant.

Developed by **Team Vyntrix — Leading University, Bangladesh**.

- Abdullah Al Mansur Showrov
- Habiba Rahman Pushpa
- Tahsin Noor Maria

## Features

| Section | What it offers |
| --- | --- |
| **Dashboard** | Balances, budget breakdowns, upcoming tuition, forecasts and deadlines. |
| **AI Workspace** | Optional conversational assistance and suggested bill fields from invoice text. |
| **Payments & Remittances** | Fictional route comparisons, separate approval and execution, and simulated receipts. |
| **Multi-Currency Intelligence** | Currency conversion, planning rates, rate targets and what-if calculations. |
| **Budget & Cash Flow** | Planned and actual spending, contributions, savings goals and reserve settings. |
| **Student Funding** | Application tracking, student checklists, income estimates and resource links. |
| **Safety & Trust** | Activity history, payment oversight and workspace data controls. |
| **Reports & Insights** | Financial summaries, CSV exports and printable reports. |
| **Learn More** | Short feature explanations with direct links to each tool. |
| **Settings** | Profile, language, display currency and time-zone preferences. |

Available in **English, Simplified Chinese, Bangla, Hindi, Arabic and
German**, with responsive layouts and right-to-left support for Arabic.

## Start Finzoria

Install **Python with the `py` launcher** and **Node.js 22.12 or newer
within the Node.js 22 series**.

Download and extract this repository, or clone it using Git.
Open PowerShell in the project folder containing `backend`, `frontend`
and `scripts`.

Install dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Start the application:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Open **http://127.0.0.1:8000** in your browser.
Keep PowerShell open while using Finzoria; press **Ctrl+C** to stop it.

No AI key is required for the financial screens. Optional assistant
configuration is described in `backend/.env.example`. Keep actual
credentials in your local `.env` file and never commit them.

## Explore the Demo

Select **Explore the demo** and choose your preferences.

Your demo workspace starts with:

- **BDT 100,000** opening balance.
- **AUD 1,000** tuition bill due six days after workspace creation.
- **BDT 20,000** reserve floor.
- **BDT 10,000** expected family contribution.

Explore the dashboard, plan a budget, switch currencies and compare
simulated tuition-payment routes. Use **Learn More** for explanations
of each feature.