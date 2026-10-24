"""Ledgerly — a small fake expense-management SaaS with deliberately planted product issues.

Each browser gets its own workspace (cookie), so concurrent agents never see each other's data.
The planted issues are listed in ground_truth.json; agents never see that file.

Run:  uvicorn demo_app.app:app --port 8100
"""

import html
import re
import uuid
from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()
WORKSPACES: dict[str, dict] = {}

CSS = """
body{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1f2933}
header{background:#123;color:#fff;padding:12px 24px;display:flex;gap:24px;align-items:center}
header a{color:#cfe3ff;text-decoration:none} header b{font-size:18px;margin-right:24px}
main{max-width:900px;margin:24px auto;background:#fff;padding:24px 32px;border-radius:8px;box-shadow:0 1px 3px #0002}
table{width:100%;border-collapse:collapse} td,th{padding:8px;border-bottom:1px solid #eee;text-align:left}
.btn{display:inline-block;background:#2563eb;color:#fff;padding:8px 14px;border-radius:6px;text-decoration:none;border:0;font-size:14px;cursor:pointer}
.btn.secondary{background:#e5e7eb;color:#111}
label{display:block;margin-top:12px;font-size:14px} input,select{padding:6px;width:280px;margin-top:4px}
.err{background:#fee;color:#900;padding:8px 12px;border-radius:6px} .ok{background:#efe;color:#060;padding:8px 12px;border-radius:6px}
.tabs a{margin-right:16px} footer{text-align:center;padding:24px;color:#9aa;font-size:9px} footer a{color:#9aa}
.tiny{font-size:9px;color:#aab} .card{border:1px solid #ddd;border-radius:8px;padding:16px;display:inline-block;width:230px;vertical-align:top;margin-right:12px}
"""


def ws(request: Request) -> tuple[str, dict]:
    wid = request.cookies.get("ws")
    if not wid or wid not in WORKSPACES:
        wid = uuid.uuid4().hex
        WORKSPACES[wid] = {
            "company": None,
            "onboarded": False,
            "expenses": [
                {"merchant": "AWS", "amount": 412.50, "date": "02/10/2026", "category": "Software", "by": "You"},
                {"merchant": "Delta Air Lines", "amount": 689.00, "date": "05/10/2026", "category": "Travel", "by": "You"},
            ],
            "cards": [],
            "members": [{"email": "you@company.com", "role": "Owner"}],
        }
    return wid, WORKSPACES[wid]


def page(request: Request, title: str, body: str, nav: bool = True) -> HTMLResponse:
    wid, _ = ws(request)
    header = (
        "<header><b>Ledgerly</b><a href='/dashboard'>Dashboard</a><a href='/expenses'>Expenses</a>"
        "<a href='/cards'>Cards</a><a href='/reports'>Reports</a><a href='/settings'>Settings</a></header>"
        if nav
        else "<header><b>Ledgerly</b></header>"
    )
    # Planted: the only route to pricing from inside the app is this tiny footer link.
    footer = "<footer>© 2026 Ledgerly Inc · <a href='/legal'>Legal</a> · <a href='/plans'>Plans</a></footer>"
    resp = HTMLResponse(f"<!doctype html><html><head><title>{title} · Ledgerly</title><style>{CSS}</style></head>"
                        f"<body>{header}<main>{body}</main>{footer}</body></html>")
    resp.set_cookie("ws", wid)
    return resp


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    wid, w = ws(request)
    target = "/dashboard" if w["onboarded"] else "/onboarding"
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie("ws", wid)
    return resp


# ---------- Onboarding (planted: forced accounting integration, tiny skip link, connection fails) ----------

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding(request: Request):
    _, w = ws(request)
    if not w["company"]:
        return page(request, "Welcome", """
            <h1>Welcome to Ledgerly 👋</h1><p>Let's set up your workspace. Step 1 of 2.</p>
            <form method="post" action="/onboarding/company">
              <label>Company name<br><input name="company" required></label>
              <label>Company size<br><select name="size"><option>1-10</option><option>11-50</option><option>51-200</option><option>200+</option></select></label>
              <p><button class="btn">Continue</button></p>
            </form>""", nav=False)
    return page(request, "Connect accounting", """
        <h1>Connect your accounting system</h1><p>Step 2 of 2. Ledgerly syncs every expense to your general ledger.
        Connect your accounting system to continue.</p>
        <p><a class="btn" href="/onboarding/connect?provider=QuickBooks">Connect QuickBooks</a>
           <a class="btn" href="/onboarding/connect?provider=Xero">Connect Xero</a>
           <a class="btn" href="/onboarding/connect?provider=NetSuite">Connect NetSuite</a></p>
        <br><br><br><br><br><br>
        <p class="tiny"><a href="/onboarding/skip" style="color:#bbc">remind me later</a></p>""", nav=False)


@app.post("/onboarding/company")
def onboarding_company(request: Request, company: str = Form(...)):
    _, w = ws(request)
    w["company"] = company
    return RedirectResponse("/onboarding", status_code=303)


@app.get("/onboarding/connect", response_class=HTMLResponse)
def onboarding_connect(request: Request, provider: str = "QuickBooks"):
    return page(request, "Connecting", f"""
        <h1>Connecting to {html.escape(provider)}…</h1>
        <p class="err">Error 502: Upstream OAuth handshake failed (code LDG-OAUTH-17). Please contact your administrator.</p>
        <p><a class="btn secondary" href="/onboarding">Back</a></p>""", nav=False)


@app.get("/onboarding/skip")
def onboarding_skip(request: Request):
    _, w = ws(request)
    w["onboarded"] = True
    return RedirectResponse("/dashboard", status_code=303)


# ---------- Dashboard ----------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    _, w = ws(request)
    if not w["onboarded"]:
        return RedirectResponse("/onboarding", status_code=303)
    total = sum(e["amount"] for e in w["expenses"])
    return page(request, "Dashboard", f"""
        <h1>{html.escape(w['company'] or 'Your company')}</h1>
        <p>Spend this month: <b>${total:,.2f}</b> across {len(w['expenses'])} expenses · {len(w['cards'])} active cards ·
        {len(w['members'])} member(s)</p>
        <p><a class="btn" href="/expenses/new">Submit an expense</a> <a class="btn secondary" href="/cards/new">Issue a card</a></p>
        <h3>Recent activity</h3>
        <table>{''.join(f"<tr><td>{e['date']}</td><td>{html.escape(e['merchant'])}</td><td>${e['amount']:,.2f}</td></tr>" for e in w['expenses'][-5:])}</table>""")


# ---------- Expenses (planted: no bulk actions, export coming soon, no approvals, hostile form) ----------

@app.get("/expenses", response_class=HTMLResponse)
def expenses(request: Request, saved: int = 0):
    _, w = ws(request)
    rows = "".join(
        f"<tr><td>{e['date']}</td><td>{html.escape(e['merchant'])}</td><td>{e['category']}</td>"
        f"<td>${e['amount']:,.2f}</td><td>{e['by']}</td><td>Approved</td><td><a href='/expenses/{i}'>View</a></td></tr>"
        for i, e in enumerate(w["expenses"])
    )
    note = "<p class='ok'>Expense submitted.</p>" if saved else ""
    return page(request, "Expenses", f"""
        <h1>Expenses</h1>{note}
        <p><a class="btn" href="/expenses/new">New expense</a> <a class="btn secondary" href="/expenses/export">Export CSV</a></p>
        <table><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th><th>Submitted by</th><th>Status</th><th></th></tr>{rows}</table>""")


@app.get("/expenses/export", response_class=HTMLResponse)
def export(request: Request):
    return page(request, "Export", "<h1>Export</h1><p>CSV export is coming soon! 🚀</p><p><a href='/expenses'>Back to expenses</a></p>")


@app.get("/expenses/new", response_class=HTMLResponse)
def new_expense(request: Request, error: int = 0):
    err = "<p class='err'>Invalid input. Please try again.</p>" if error else ""
    return page(request, "New expense", f"""
        <h1>New expense</h1>{err}
        <form method="post" action="/expenses/new">
          <label>Merchant<br><input name="merchant" required></label>
          <label>Amount<br><input name="amount" required></label>
          <label>Transaction date<br><input name="date" required></label>
          <label>Category<br><select name="category"><option>Software</option><option>Travel</option><option>Meals</option><option>Office</option><option>Other</option></select></label>
          <label>Cost center code<br><input name="cost_center" required></label>
          <p><button class="btn">Submit</button></p>
        </form>""")


@app.post("/expenses/new")
def create_expense(request: Request, merchant: str = Form(""), amount: str = Form(""), date: str = Form(""),
                   category: str = Form("Other"), cost_center: str = Form("")):
    _, w = ws(request)
    # Planted: date must be DD/MM/YYYY and cost center must be CC-####; neither is explained,
    # the error is generic and the form is cleared.
    try:
        amt = float(amount.replace("$", "").replace(",", ""))
        datetime.strptime(date, "%d/%m/%Y")
        assert re.fullmatch(r"CC-\d{4}", cost_center.strip())
    except Exception:  # noqa: BLE001
        return RedirectResponse("/expenses/new?error=1", status_code=303)
    w["expenses"].append({"merchant": merchant, "amount": amt, "date": date, "category": category, "by": "You"})
    return RedirectResponse("/expenses?saved=1", status_code=303)


@app.get("/expenses/{idx}", response_class=HTMLResponse)
def view_expense(request: Request, idx: int):
    _, w = ws(request)
    e = w["expenses"][idx]
    return page(request, "Expense", f"""
        <h1>{html.escape(e['merchant'])}</h1><p>${e['amount']:,.2f} · {e['date']} · {e['category']}</p>
        <p>Status: Approved (auto)</p><p><a href='/expenses'>Back</a></p>""")


# ---------- Cards (works fine: a control flow) ----------

@app.get("/cards", response_class=HTMLResponse)
def cards(request: Request):
    _, w = ws(request)
    rows = "".join(f"<tr><td>{html.escape(c['holder'])}</td><td>•••• {c['last4']}</td><td>${c['limit']:,}/mo</td></tr>" for c in w["cards"])
    return page(request, "Cards", f"""
        <h1>Cards</h1><p><a class="btn" href="/cards/new">Issue a card</a></p>
        <table><tr><th>Cardholder</th><th>Card</th><th>Monthly limit</th></tr>{rows or '<tr><td colspan=3>No cards yet.</td></tr>'}</table>""")


@app.get("/cards/new", response_class=HTMLResponse)
def new_card(request: Request):
    return page(request, "Issue card", """
        <h1>Issue a virtual card</h1>
        <form method="post" action="/cards/new">
          <label>Cardholder name<br><input name="holder" required></label>
          <label>Monthly limit (USD)<br><input name="limit" type="number" value="1000" required></label>
          <p><button class="btn">Issue card</button></p>
        </form>""")


@app.post("/cards/new")
def create_card(request: Request, holder: str = Form(...), limit: int = Form(1000)):
    _, w = ws(request)
    w["cards"].append({"holder": holder, "limit": limit, "last4": str(uuid.uuid4().int)[-4:]})
    return RedirectResponse("/cards", status_code=303)


# ---------- Reports ----------

@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    _, w = ws(request)
    by_cat: dict[str, float] = {}
    for e in w["expenses"]:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
    rows = "".join(f"<tr><td>{c}</td><td>${v:,.2f}</td></tr>" for c, v in sorted(by_cat.items(), key=lambda x: -x[1]))
    return page(request, "Reports", f"<h1>Spending by category</h1><table>{rows}</table>")


# ---------- Settings (planted: team invites buried under jargon; no audit log; billing hides pricing) ----------

SETTINGS_TABS = ("<p class='tabs'><a href='/settings'>Profile</a><a href='/settings/notifications'>Notifications</a>"
                 "<a href='/settings/workspace'>Workspace Administration</a><a href='/settings/billing'>Billing &amp; Subscription</a></p><hr>")


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return page(request, "Settings", f"""<h1>Settings</h1>{SETTINGS_TABS}
        <form><label>Your name<br><input value="You"></label><label>Email<br><input value="you@company.com"></label>
        <label>Timezone<br><select><option>UTC</option><option>America/New_York</option></select></label></form>""")


@app.get("/settings/notifications", response_class=HTMLResponse)
def notifications(request: Request):
    return page(request, "Notifications", f"""<h1>Settings</h1>{SETTINGS_TABS}
        <label><input type="checkbox" checked style="width:auto"> Email me a weekly spend summary</label>
        <label><input type="checkbox" style="width:auto"> Email me when a card is declined</label>""")


@app.get("/settings/workspace", response_class=HTMLResponse)
def workspace(request: Request):
    return page(request, "Workspace Administration", f"""<h1>Settings</h1>{SETTINGS_TABS}
        <h3>Workspace Administration</h3>
        <ul><li><a href="/settings/workspace/general">General</a></li>
            <li><a href="/settings/workspace/seats">Seats &amp; Provisioning</a></li>
            <li><a href="/settings/workspace/ledger">Ledger Mapping</a></li>
            <li><a href="/settings/workspace/sso">Identity Federation</a></li></ul>""")


@app.get("/settings/workspace/general", response_class=HTMLResponse)
def ws_general(request: Request):
    _, w = ws(request)
    return page(request, "General", f"""<h1>Settings</h1>{SETTINGS_TABS}<h3>General</h3>
        <label>Workspace name<br><input value="{html.escape(w['company'] or '')}"></label>
        <label>Base currency<br><select><option>USD</option><option>EUR</option></select></label>""")


@app.get("/settings/workspace/seats", response_class=HTMLResponse)
def seats(request: Request, added: int = 0):
    _, w = ws(request)
    rows = "".join(f"<tr><td>{html.escape(m['email'])}</td><td>{m['role']}</td></tr>" for m in w["members"])
    note = "<p class='ok'>Seat provisioned. An activation email was sent.</p>" if added else ""
    return page(request, "Seats & Provisioning", f"""<h1>Settings</h1>{SETTINGS_TABS}
        <h3>Seats &amp; Provisioning</h3>{note}<table><tr><th>Principal</th><th>Entitlement</th></tr>{rows}</table>
        <form method="post" action="/settings/workspace/seats">
          <label>Principal identifier<br><input name="email" required></label>
          <label>Entitlement<br><select name="role"><option>Submitter</option><option>Approver</option><option>Admin</option></select></label>
          <p><button class="btn">Provision seat</button></p></form>""")


@app.post("/settings/workspace/seats")
def add_seat(request: Request, email: str = Form(...), role: str = Form("Submitter")):
    _, w = ws(request)
    w["members"].append({"email": email, "role": role})
    return RedirectResponse("/settings/workspace/seats?added=1", status_code=303)


@app.get("/settings/workspace/ledger", response_class=HTMLResponse)
def ledger(request: Request):
    return page(request, "Ledger Mapping", f"""<h1>Settings</h1>{SETTINGS_TABS}<h3>Ledger Mapping</h3>
        <p>No accounting system connected. <a href="/onboarding/connect?provider=QuickBooks">Connect QuickBooks</a></p>""")


@app.get("/settings/workspace/sso", response_class=HTMLResponse)
def sso(request: Request):
    return page(request, "Identity Federation", f"""<h1>Settings</h1>{SETTINGS_TABS}<h3>Identity Federation</h3>
        <p>SAML SSO is available on the Scale plan.</p>""")


@app.get("/settings/billing", response_class=HTMLResponse)
def billing(request: Request):
    return page(request, "Billing", f"""<h1>Settings</h1>{SETTINGS_TABS}<h3>Billing &amp; Subscription</h3>
        <p>Current plan: <b>Trial</b> (13 days remaining)</p>
        <p><a class="btn secondary" href="/settings/billing/manage">Manage subscription</a></p>""")


@app.get("/settings/billing/manage", response_class=HTMLResponse)
def billing_manage(request: Request):
    return page(request, "Manage subscription", f"""<h1>Settings</h1>{SETTINGS_TABS}
        <p>To change your subscription, please contact your Ledgerly account representative.</p>""")


@app.get("/plans", response_class=HTMLResponse)
def plans(request: Request):
    return page(request, "Plans", """<h1>Plans</h1>
        <div class="card"><h3>Starter</h3><p><b>$0</b></p><p>Up to 3 users. Expense submission.</p></div>
        <div class="card"><h3>Growth</h3><p><b>$12</b>/user/mo*</p><p>Cards, reports, accounting sync.</p></div>
        <div class="card"><h3>Scale</h3><p><b>Contact sales</b></p><p>SSO, advanced controls.</p></div>
        <p class="tiny">* Billed annually. Minimum 10 seats. Taxes not included.</p>""")


@app.get("/legal", response_class=HTMLResponse)
def legal(request: Request):
    return page(request, "Legal", "<h1>Legal</h1><p>Terms of service and privacy policy.</p>")
