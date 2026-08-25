
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlite3
import json
from datetime import datetime
import pytz

app = FastAPI()
IST = pytz.timezone('Asia/Kolkata')

def init_db():
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS products 
                     (code TEXT PRIMARY KEY, name TEXT, unit TEXT, price REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS customers 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE, balance REAL DEFAULT 0.0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS customer_ledger 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      customer_id INTEGER, 
                      txn_date TEXT, 
                      description TEXT, 
                      debit REAL DEFAULT 0.0, 
                      credit REAL DEFAULT 0.0, 
                      balance REAL DEFAULT 0.0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bills 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      bill_no INTEGER, 
                      bill_date_key TEXT, 
                      customer_type TEXT, 
                      customer_name TEXT, 
                      items TEXT, 
                      total REAL, 
                      paid REAL DEFAULT 0.0,
                      time_str TEXT)""")
        
        c.executemany("INSERT OR IGNORE INTO products VALUES (?,?,?,?)", [
            ('101', 'சீரகம்', 'Kg', 600.0),
            ('102', 'மிளகு', 'Kg', 900.0),
            ('103', 'கடலை எண்ணெய்', 'L', 180.0),
            ('104', 'தேங்காய் எண்ணெய்', 'L', 220.0),
            ('105', 'கோல்கேட் பேஸ்ட்', 'Pcs', 45.0),
            ('106', 'துவரம் பருப்பு', 'Kg', 160.0)
        ])
        conn.commit()

init_db()

@app.get("/api/data")
def get_data():
    with sqlite3.connect("store.db", timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT code, name, unit, price FROM products ORDER BY rowid DESC")
        products = [dict(r) for r in c.fetchall()]
        
        c.execute("SELECT id, name, balance FROM customers ORDER BY name COLLATE NOCASE ASC")
        customers = [dict(r) for r in c.fetchall()]
        
        c.execute("SELECT id, bill_no, bill_date_key, customer_type, customer_name, items, total, paid, time_str FROM bills ORDER BY id DESC LIMIT 50")
        raw_bills = c.fetchall()
        bills = []
        for r in raw_bills:
            d = dict(r)
            d['items'] = json.loads(d['items'])
            bills.append(d)
        return {"products": products, "customers": customers, "bills": bills}

@app.get("/api/customer/ledger/{cid}")
def get_customer_ledger(cid: int):
    with sqlite3.connect("store.db", timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT txn_date, description, debit, credit, balance FROM customer_ledger WHERE customer_id=? ORDER BY id DESC", (cid,))
        ledger = [dict(r) for r in c.fetchall()]
        return {"ledger": ledger}

class ProductItem(BaseModel):
    code: str
    name: str
    unit: str
    price: float

@app.post("/api/product")
def update_product(p: ProductItem):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO products (code, name, unit, price) VALUES (?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name, unit=excluded.unit, price=excluded.price", 
                  (p.code.strip(), p.name.strip(), p.unit, p.price))
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/product/{code}")
def delete_product(code: str):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE code=?", (code.strip(),))
        conn.commit()
    return {"status": "ok"}

class CustomerModel(BaseModel):
    id: int = 0
    name: str
    balance: float

@app.post("/api/customer")
def save_customer(cu: CustomerModel):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        now_str = datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")
        c_name = cu.name.strip()
        
        if cu.id > 0:
            c.execute("UPDATE customers SET name=?, balance=? WHERE id=?", (c_name, cu.balance, cu.id))
            c.execute("INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) VALUES (?,?,?,?,?,?)",
                      (cu.id, now_str, "விவரம் திருத்தம் (Manual Edit)", 0.0, 0.0, cu.balance))
        else:
            c.execute("SELECT id FROM customers WHERE name=?", (c_name,))
            if c.fetchone():
                return {"status": "exists", "msg": f"'{c_name}' பெயரில் ஏற்கெனவே கணக்கு உள்ளது!"}
            
            c.execute("INSERT INTO customers (name, balance) VALUES (?,?)", (c_name, cu.balance))
            new_cid = c.lastrowid
            c.execute("INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) VALUES (?,?,?,?,?,?)",
                      (new_cid, now_str, "தொடக்கக் கணக்கு", 0.0, 0.0, cu.balance))
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/customer/{cid}")
def delete_customer(cid: int):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM customers WHERE id=?", (cid,))
        c.execute("DELETE FROM customer_ledger WHERE customer_id=?", (cid,))
        conn.commit()
    return {"status": "ok"}

class PaymentModel(BaseModel):
    customer_id: int
    amount: float

@app.post("/api/customer/payment")
def add_payment(p: PaymentModel):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM customers WHERE id=?", (p.customer_id,))
        row = c.fetchone()
        if row:
            cur_bal = row[0]
            new_bal = cur_bal - p.amount
            now_str = datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")
            c.execute("UPDATE customers SET balance=? WHERE id=?", (new_bal, p.customer_id))
            c.execute("INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) VALUES (?,?,?,?,?,?)",
                      (p.customer_id, now_str, "நேரடி ரொக்க வரவு (Cash Paid)", 0.0, p.amount, new_bal))
            conn.commit()
    return {"status": "ok"}

class BillRequest(BaseModel):
    customer_type: str
    customer_name: str
    items: list
    total: float
    paid: float

@app.post("/api/bill")
def save_bill(b: BillRequest):
    with sqlite3.connect("store.db", timeout=30) as conn:
        c = conn.cursor()
        now_ist = datetime.now(IST)
        date_key = now_ist.strftime("%Y-%m-%d")
        time_str = now_ist.strftime("%d-%m-%Y %I:%M:%S %p")
        
        c.execute("SELECT MAX(bill_no) FROM bills WHERE bill_date_key=?", (date_key,))
        row = c.fetchone()
        daily_bill_no = (row[0] + 1) if (row and row[0] is not None) else 1
        
        c.execute("""INSERT INTO bills (bill_no, bill_date_key, customer_type, customer_name, items, total, paid, time_str)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (daily_bill_no, date_key, b.customer_type, b.customer_name, json.dumps(b.items), b.total, b.paid, time_str))
        
        if b.customer_type == "ரெகுலர் கஸ்டமர்" and b.customer_name:
            c.execute("SELECT id, balance FROM customers WHERE name=?", (b.customer_name.strip(),))
            cust_row = c.fetchone()
            if cust_row:
                cid = cust_row[0]
                old_bal = cust_row[1]
                net_add = b.total - b.paid
                new_bal = old_bal + net_add
                c.execute("UPDATE customers SET balance=? WHERE id=?", (new_bal, cid))
                c.execute("""INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance)
                             VALUES (?,?,?,?,?,?)""",
                          (cid, now_ist.strftime("%d-%m-%Y %I:%M:%S %p"), f"பில் எண் #{daily_bill_no}", b.total, b.paid, new_bal))
            
        conn.commit()
    return {"status": "ok", "bill_no": daily_bill_no, "time": time_str}

@app.get("/", response_class=HTMLResponse)
def get_ui():
    return """
    <!DOCTYPE html>
    <html lang="ta">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
      <title>KSA மளிகை - திருமயம்</title>
      <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: #f8fafc; color: #1e293b; padding: 6px; -webkit-tap-highlight-color: transparent; }
        .app-container { max-width: 480px; margin: auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
        
        .header { background: #2563eb; color: #ffffff; padding: 14px 10px; text-align: center; }
        .header h1 { font-size: 1.25rem; font-weight: 800; }
        .header p { font-size: 11px; color: #dbeafe; margin-top: 2px; }
        
        .nav-tabs { display: flex; background: #f1f5f9; padding: 4px; gap: 4px; border-bottom: 1px solid #e2e8f0; }
        .tab-btn { flex: 1; padding: 10px 2px; border: none; background: transparent; font-size: 11px; font-weight: 700; border-radius: 8px; cursor: pointer; color: #64748b; }
        .tab-btn.active { background: #ffffff; color: #2563eb; box-shadow: 0 2px 4px rgba(0,0,0,0.06); }
        
        .view-panel { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
        .hidden { display: none !important; }
        
        .box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; }
        .input-group { display: flex; gap: 6px; margin-bottom: 6px; }
        input, select { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-weight: 600; outline: none; background: #ffffff; color: #1e293b; }
        input:focus, select:focus { border-color: #3b82f6; }
        
        .btn { padding: 10px 14px; border: none; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; text-align: center; transition: all 0.1s; }
        .btn:active { transform: scale(0.98); }
        .btn-blue { background: #2563eb; color: #ffffff; }
        .btn-soft-blue { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
        .btn-green { background: #16a34a; color: #ffffff; }
        .btn-soft-green { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
        .btn-amber { background: #d97706; color: #ffffff; }
        .btn-soft-amber { background: #fffbeb; color: #d97706; border: 1px solid #fde68a; }
        .btn-red { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
        
        .unit-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin: 6px 0; }
        .unit-grid button { padding: 8px 0; border: 1px solid #cbd5e1; background: #ffffff; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; color: #334155; }
        .unit-grid button:active { background: #dbeafe; color: #1d4ed8; }
        
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th, td { padding: 8px 6px; text-align: left; border-bottom: 1px solid #f1f5f9; }
        th { background: #f8fafc; font-weight: 700; color: #475569; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        
        .total-box { background: #1e293b; color: #ffffff; padding: 12px; border-radius: 10px; }
        .action-btns { display: flex; gap: 8px; margin-top: 4px; }
        
        .modal { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.5); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; padding: 12px; z-index: 100; }
        .modal-content { background: #ffffff; border-radius: 14px; max-width: 440px; width: 100%; max-height: 85vh; display: flex; flex-direction: column; overflow: hidden; padding: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        
        @media print {
          body * { visibility: hidden; }
          #receipt, #receipt * { visibility: visible; }
          #receipt { position: absolute; left: 0; top: 0; width: 72mm; font-family: monospace; font-size: 12px; font-weight: 900; color: #000000; line-height: 1.25; display: block !important; padding: 4px; }
          #receipt table { width: 100%; font-size: 11px; }
          #receipt .border-b { border-bottom: 1.5px dashed #000000; margin: 4px 0; }
        }
      </style>
    </head>
    <body>
      <div class="app-container">
        
        <div class="header">
          <h1>🏪 KSA மளிகை, திருமயம்</h1>
          <p>அதிவேக மொபைல் பில்லிங் & பாஸ்புக் PDF</p>
        </div>

        <div class="nav-tabs">
          <button onclick="switchTab('pos')" id="tabPos" class="tab-btn active">🛒 பில்லிங்</button>
          <button onclick="switchTab('prods')" id="tabProds" class="tab-btn">🏷️ பொருட்கள்</button>
          <button onclick="switchTab('ledger')" id="tabLedger" class="tab-btn">📒 கஸ்டமர் பாஸ்புக்</button>
          <button onclick="switchTab('history')" id="tabHistory" class="tab-btn">📜 ஹிஸ்டரி</button>
        </div>

        <!-- 1. POS TAB -->
        <div id="viewPos" class="view-panel">
          <div class="box" style="background: #eff6ff; border-color: #bfdbfe;">
            <div class="input-group">
              <select id="custType" onchange="onCustTypeChange()">
                <option value="கஸ்டமர்">கஸ்டமர் (ரொக்கம்)</option>
                <option value="ரெகுலர் கஸ்டமர்">ரெகுலர் கஸ்டமர் (பாக்கி)</option>
              </select>
            </div>
            <div id="regularCustDiv" class="hidden" style="margin-top: 6px;">
              <select id="regularCustSelect" onchange="updatePosCustInfo()"></select>
              <div id="posCustBalBadge" style="font-size: 11px; font-weight: 800; color: #dc2626; margin-top: 4px;"></div>
            </div>
          </div>

          <div class="box">
            <div class="input-group">
              <input type="text" id="pCode" placeholder="Code" style="flex: 1; text-align: center;" oninput="findProductByCode()">
              <input type="text" list="productListDatalist" id="pName" placeholder="பொருள் பெயர்" style="flex: 2.2;" oninput="findProductByName()">
              <datalist id="productListDatalist"></datalist>
            </div>
            <div class="input-group">
              <input type="number" id="pRate" placeholder="₹ விலை" oninput="recalcItemTotal()" style="flex: 1;">
              <input type="number" id="pQty" step="any" placeholder="அளவு" oninput="recalcItemTotal()" style="flex: 1; text-align: center;">
              <input type="number" id="pTotalAmt" placeholder="தொகை ₹" style="flex: 1.2; text-align: right; background: #fef9c3; font-weight: 900; color: #854d0e;">
            </div>
            <div id="unitButtonsArea" class="unit-grid"></div>
            <button onclick="addToBill()" class="btn btn-green" style="width: 100%; margin-top: 4px;">➕ பில்லில் சேர் (Add Item)</button>
          </div>

          <div style="border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden;">
            <table>
              <thead>
                <tr>
                  <th>பொருள்</th>
                  <th class="text-center">அளவு</th>
                  <th class="text-right">விலை</th>
                  <th class="text-right">மொத்தம்</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="cartTable"></tbody>
            </table>
          </div>

          <div class="total-box">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; color: #cbd5e1;">பில் மொத்தம்:</span>
              <span style="font-size: 1.3rem; font-weight: 900; color: #facc15;">₹<span id="billTotal">0.00</span></span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155;">
              <span style="font-size: 12px; color: #4ade80; font-weight: 700;">இப்போது கொடுத்த வரவு:</span>
              <input type="number" id="billPaidAmt" value="0" style="width: 90px; text-align: right; padding: 6px; background: #0f172a; color: #ffffff; border: 1px solid #475569; border-radius: 6px;">
            </div>
          </div>

          <div class="action-btns">
            <button onclick="completeBill(false)" class="btn btn-blue" style="flex: 1; padding: 12px;">🖨️ பிரிண்ட் (Print)</button>
            <button onclick="completeBill(true)" class="btn btn-soft-amber" style="flex: 1; padding: 12px;">📥 PDF பில் (Save)</button>
          </div>
        </div>

        <!-- 2. PRODUCTS TAB -->
        <div id="viewProds" class="view-panel hidden">
          <div class="box" style="background: #f0fdf4; border-color: #bbf7d0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span id="prodFormTitle" style="font-size: 11px; font-weight: 800; color: #166534;">➕ புதிய பொருள் / விலை திருத்தம்</span>
              <span id="prodEditBadge" class="hidden" style="font-size: 10px; background: #bbf7d0; padding: 2px 6px; border-radius: 4px; font-weight: 800; color: #166534;">Editing</span>
            </div>
            <div class="input-group">
              <input type="text" id="npCode" placeholder="Code (107)" style="flex: 1;">
              <input type="text" id="npName" placeholder="பொருள் பெயர்" style="flex: 2;">
            </div>
            <div class="input-group">
              <select id="npUnit" style="flex: 1;">
                <option value="Kg">கிலோ (Kg/g)</option>
                <option value="L">லிட்டர் (L/ml)</option>
                <option value="Pcs">எண்ணிக்கை (Pcs)</option>
              </select>
              <input type="number" id="npRate" placeholder="விலை ₹" style="flex: 1;">
            </div>
            <div style="display: flex; gap: 6px;">
              <button onclick="saveProduct()" id="btnSaveProd" class="btn btn-green" style="flex: 1;">💾 பொருள் சேமி</button>
              <button onclick="clearProdForm()" class="btn" style="background: #e2e8f0;">Clear</button>
            </div>
          </div>
          <h4 style="font-size: 11px; color: #64748b; margin-top: 4px;">பொருட்கள் பட்டியல்:</h4>
          <div id="prodList" style="display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto;"></div>
        </div>

        <!-- 3. CUSTOMER LEDGER TAB -->
        <div id="viewLedger" class="view-panel hidden">
          <div class="box" style="background: #fffbeb; border-color: #fde68a;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span id="custFormTitle" style="font-size: 11px; font-weight: 800; color: #92400e;">➕ புதிய வாடிக்கையாளர் சேர்க்க:</span>
              <span id="custEditBadge" class="hidden" style="font-size: 10px; background: #fde68a; padding: 2px 6px; border-radius: 4px; font-weight: 800; color: #92400e;">Editing</span>
            </div>
            <input type="hidden" id="ncId" value="0">
            <div class="input-group">
              <input type="text" id="ncName" placeholder="கஸ்டமர் / ஹோட்டல் பெயர்" style="flex: 2;">
              <input type="number" id="ncBal" placeholder="பாக்கி ₹" value="0" style="flex: 1;">
            </div>
            <div style="display: flex; gap: 6px;">
              <button onclick="saveCustomer()" id="btnSaveCust" class="btn btn-amber" style="flex: 1;">💾 சேமி (Save)</button>
              <button onclick="clearCustForm()" class="btn" style="background: #e2e8f0;">Clear / New</button>
            </div>
          </div>

          <div class="box" style="background: #f0fdf4; border-color: #bbf7d0;">
            <span style="font-size: 11px; font-weight: 700; color: #166534;">💵 நேரடி ரொக்க வரவு வைக்க:</span>
            <div class="input-group" style="margin-top: 6px;">
              <select id="payCustSelect" style="flex: 1.6;"></select>
              <input type="number" id="payAmount" placeholder="வரவு ₹" style="flex: 1;">
            </div>
            <button onclick="submitDirectPayment()" class="btn btn-soft-green" style="width: 100%; margin-top: 4px; font-weight: 800;">✅ வரவு ஏற்று (Record Payment)</button>
          </div>

          <h4 style="font-size: 11px; color: #64748b; margin-top: 4px;">வாடிக்கையாளர்கள் பட்டியல்:</h4>
          <div id="ledgerList" style="display: flex; flex-direction: column; gap: 6px; max-height: 280px; overflow-y: auto;"></div>

          <!-- Passbook Modal (With Direct PDF Download Button) -->
          <div id="passbookModal" class="modal hidden">
            <div class="modal-content">
              <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">
                <div>
                  <h3 id="pbCustName" style="font-size: 13px; font-weight: 800; color: #1e3a8a;"></h3>
                  <p id="pbCustBal" style="font-size: 11px; font-weight: 800; color: #dc2626; margin-top: 2px;"></p>
                </div>
                <button onclick="closePassbook()" class="btn btn-red" style="padding: 4px 8px; font-size: 11px;">✕ Close</button>
              </div>
              
              <!-- PDF & Print Buttons inside Passbook -->
              <div style="display: flex; gap: 6px; margin-top: 8px;">
                <button onclick="downloadPassbookPdf()" class="btn btn-soft-amber" style="flex: 1; padding: 8px; font-size: 12px;">📥 பாஸ்புக் PDF (Download)</button>
              </div>

              <!-- Passbook Printable Area -->
              <div id="passbookPrintArea" style="overflow-y: auto; flex: 1; margin-top: 8px; background: #ffffff; padding: 4px;">
                <div id="pbHeaderPrint" style="display: none; text-align: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-bottom: 6px;">
                  <h2 style="font-size: 14px; font-weight: 900;">KSA மளிகை - கஸ்டமர் பாஸ்புக்</h2>
                  <p id="pbPrintCustInfo" style="font-size: 11px; font-weight: 700; color: #1e3a8a;"></p>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>தேதி & நேரம்</th>
                      <th>விவரம்</th>
                      <th class="text-right">பில் (Dr)</th>
                      <th class="text-right">வரவு (Cr)</th>
                      <th class="text-right">பாக்கி</th>
                    </tr>
                  </thead>
                  <tbody id="pbTableBody"></tbody>
                </table>
              </div>
            </div>
          </div>

        </div>

        <!-- 4. HISTORY TAB -->
        <div id="viewHistory" class="view-panel hidden">
          <div id="billHistoryList" style="display: flex; flex-direction: column; gap: 6px; max-height: 400px; overflow-y: auto;"></div>
        </div>

      </div>

      <!-- Clean Receipt Template -->
      <div id="receipt" style="display: none; background: #ffffff; padding: 6px; width: 72mm; color: #000000;">
        <div style="text-align: center; font-size: 14px; font-weight: 900;">KSA மளிகை, திருமயம்</div>
        <div class="border-b"></div>
        <div style="display: flex; justify-content: space-between;"><span>பில் எண்: <b id="rBillNo"></b></span></div>
        <div style="display: flex; justify-content: space-between;"><span>தேதி: <b id="rTime"></b></span></div>
        <div>கஸ்டமர்: <b id="rCust"></b></div>
        <div class="border-b"></div>
        <table style="width: 100%;"><tbody id="rItems"></tbody></table>
        <div class="border-b"></div>
        <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 900;">
          <span>மொத்தம்:</span><span>₹<span id="rTotal"></span></span>
        </div>
        <div id="rPaidRow" style="display: flex; justify-content: space-between; font-size: 11px;">
          <span>வரவு (Paid):</span><span>₹<span id="rPaid"></span></span>
        </div>
        <div class="border-b"></div>
        <div style="text-align: center; font-size: 10px; margin-top: 4px;">நன்றி! மீண்டும் வருக!</div>
      </div>

      <script>
        let db = { products: [], customers: [], bills: [] };
        let cart = [];
        let currentItemUnit = 'Kg';
        let currentOpenCust = { id: 0, name: '', balance: 0 };

        async function fetchAll() {
          try {
            let res = await fetch('/api/data');
            db = await res.json();
            renderCustomerDropdowns();
            renderProductDatalist();
            renderProductList();
            renderLedgerList();
            renderHistoryList();
          } catch(e) { console.error(e); }
        }
        fetchAll();

        function renderCustomerDropdowns() {
          let sel = document.getElementById('regularCustSelect');
          let paySel = document.getElementById('payCustSelect');
          sel.innerHTML = '';
          paySel.innerHTML = '';
          if (!db.customers || db.customers.length === 0) {
            sel.innerHTML = '<option value="">வாடிக்கையாளர்கள் இல்லை</option>';
            paySel.innerHTML = '<option value="">வாடிக்கையாளர்கள் இல்லை</option>';
          } else {
            db.customers.forEach(c => {
              sel.innerHTML += `<option value="${c.name}" data-bal="${c.balance}">${c.name}</option>`;
              paySel.innerHTML += `<option value="${c.id}">${c.name} (பாக்கி: ₹${c.balance})</option>`;
            });
          }
          updatePosCustInfo();
        }

        function updatePosCustInfo() {
          let sel = document.getElementById('regularCustSelect');
          if(sel && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex] && sel.value !== '') {
            let bal = parseFloat(sel.options[sel.selectedIndex].dataset.bal || 0);
            document.getElementById('posCustBalBadge').innerText = '📌 முந்தைய பாக்கி: ₹' + bal.toFixed(2);
          } else {
            document.getElementById('posCustBalBadge').innerText = '';
          }
        }

        function onCustTypeChange() {
          let ctype = document.getElementById('custType').value;
          let regDiv = document.getElementById('regularCustDiv');
          if(ctype === 'ரெகுலர் கஸ்டமர்') {
            regDiv.classList.remove('hidden');
            updatePosCustInfo();
          } else {
            regDiv.classList.add('hidden');
          }
        }

        function renderProductDatalist() {
          let dl = document.getElementById('productListDatalist');
          dl.innerHTML = '';
          db.products.forEach(p => {
            dl.innerHTML += `<option value="${p.name}">[${p.code}] - ₹${p.price}/${p.unit}</option>`;
          });
        }

        function findProductByCode() {
          let code = document.getElementById('pCode').value.trim();
          let p = db.products.find(x => String(x.code).toLowerCase() === code.toLowerCase());
          if(p) setProductFields(p);
        }

        function findProductByName() {
          let name = document.getElementById('pName').value.trim();
          let p = db.products.find(x => x.name.toLowerCase() === name.toLowerCase());
          if(p) {
            document.getElementById('pCode').value = p.code;
            setProductFields(p);
          }
        }

        function setProductFields(p) {
          document.getElementById('pName').value = p.name;
          document.getElementById('pRate').value = p.price;
          document.getElementById('pQty').value = 1.0;
          currentItemUnit = p.unit || 'Kg';
          renderUnitButtons(currentItemUnit);
          recalcItemTotal();
        }

        function renderUnitButtons(u) {
          let area = document.getElementById('unitButtonsArea');
          if(u === 'Kg') {
            area.innerHTML = `
              <button onclick="setQty(0.05, '50g')">50g</button>
              <button onclick="setQty(0.10, '100g')">100g</button>
              <button onclick="setQty(0.25, '1/4 kg')">1/4 kg</button>
              <button onclick="setQty(0.50, '1/2 kg')">1/2 kg</button>
              <button onclick="setQty(1.00, '1 Kg')" style="background:#eff6ff; color:#2563eb; border-color:#bfdbfe;">1 Kg</button>`;
          } else if(u === 'L') {
            area.innerHTML = `
              <button onclick="setQty(0.10, '100 ml')">100ml</button>
              <button onclick="setQty(0.25, '1/4 L')">1/4 L</button>
              <button onclick="setQty(0.50, '1/2 L')">1/2 L</button>
              <button onclick="setQty(1.00, '1 L')" style="background:#eff6ff; color:#2563eb; border-color:#bfdbfe;">1 L</button>
              <button onclick="setQty(2.00, '2 L')">2 L</button>`;
          } else {
            area.innerHTML = `
              <button onclick="setQty(1, '1 Pcs')">1</button>
              <button onclick="setQty(2, '2 Pcs')">2</button>
              <button onclick="setQty(5, '5 Pcs')">5</button>
              <button onclick="setQty(10, '10 Pcs')" style="background:#eff6ff; color:#2563eb; border-color:#bfdbfe;">10</button>
              <button onclick="setQty(20, '20 Pcs')">20</button>`;
          }
        }

        let customDisplayLabel = '';
        function setQty(q, label) {
          document.getElementById('pQty').value = q;
          customDisplayLabel = label;
          recalcItemTotal();
        }

        function recalcItemTotal() {
          let rate = parseFloat(document.getElementById('pRate').value) || 0;
          let qty = parseFloat(document.getElementById('pQty').value) || 0;
          document.getElementById('pTotalAmt').value = Math.round(rate * qty);
        }

        function addToBill() {
          let name = document.getElementById('pName').value.trim();
          let rate = parseFloat(document.getElementById('pRate').value);
          let qty = parseFloat(document.getElementById('pQty').value);
          let tot = parseFloat(document.getElementById('pTotalAmt').value);
          if(!name || isNaN(rate) || isNaN(qty) || isNaN(tot)) return alert('விவரங்களை உள்ளிடவும்!');
          
          let displayQty = customDisplayLabel || (qty + ' ' + currentItemUnit);
          cart.push({ name, rate, qty, unit: currentItemUnit, displayQty, tot });
          renderCart();
          
          document.getElementById('pCode').value = '';
          document.getElementById('pName').value = '';
          document.getElementById('pRate').value = '';
          document.getElementById('pQty').value = '';
          document.getElementById('pTotalAmt').value = '';
          document.getElementById('unitButtonsArea').innerHTML = '';
          customDisplayLabel = '';
        }

        function renderCart() {
          let h = '';
          let sum = 0;
          cart.forEach((it, i) => {
            sum += it.tot;
            h += `<tr>
              <td><b>${it.name}</b></td>
              <td class="text-center">${it.displayQty}</td>
              <td class="text-right">₹${it.rate}</td>
              <td class="text-right" style="color: #2563eb; font-weight: 800;">₹${it.tot}</td>
              <td class="text-center"><button onclick="cart.splice(${i},1); renderCart();" style="border:none; background:transparent; color:#dc2626; font-weight:800; font-size:14px; cursor:pointer;">✕</button></td>
            </tr>`;
          });
          document.getElementById('cartTable').innerHTML = h;
          document.getElementById('billTotal').innerText = sum.toFixed(2);
        }

        async function completeBill(downloadPdf = false) {
          if(cart.length === 0) return alert('பில்லில் பொருள் சேர்க்கவும்!');
          let ctype = document.getElementById('custType').value;
          let cname = ctype === 'ரெகுலர் கஸ்டமர்' ? document.getElementById('regularCustSelect').value : 'பொது வாடிக்கையாளர்';
          if(ctype === 'ரெகுலர் கஸ்டமர்' && (!cname || cname === '')) return alert('வாடிக்கையாளரைத் தேர்வு செய்யவும்!');
          
          let total = parseFloat(document.getElementById('billTotal').innerText);
          let paid = parseFloat(document.getElementById('billPaidAmt').value) || 0;

          let res = await fetch('/api/bill', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ customer_type: ctype, customer_name: cname, items: cart, total: total, paid: paid })
          });
          let out = await res.json();
          if(out.status === 'ok') {
            generateOutput(out.bill_no, out.time, ctype, cname, cart, total, paid, downloadPdf);
            cart = [];
            document.getElementById('billPaidAmt').value = 0;
            renderCart();
            await fetchAll();
          }
        }

        function generateOutput(billNo, timeStr, ctype, cname, items, total, paid, downloadPdf) {
          document.getElementById('rBillNo').innerText = '#' + billNo;
          document.getElementById('rTime').innerText = timeStr;
          document.getElementById('rCust').innerText = cname + (ctype === 'ரெகுலர் கஸ்டமர்' ? ' (கடன்)' : '');
          let rRows = '';
          items.forEach(it => {
            rRows += `<tr><td>${it.name} (${it.displayQty})</td><td style="text-align: right;">₹${it.tot}</td></tr>`;
          });
          document.getElementById('rItems').innerHTML = rRows;
          document.getElementById('rTotal').innerText = total;
          if(paid > 0) {
            document.getElementById('rPaidRow').style.display = 'flex';
            document.getElementById('rPaid').innerText = paid;
          } else {
            document.getElementById('rPaidRow').style.display = 'none';
          }

          let receiptElem = document.getElementById('receipt');
          
          if(downloadPdf) {
            receiptElem.style.display = 'block';
            let opt = {
              margin: 2,
              filename: `Bill_${billNo}_${cname}.pdf`,
              image: { type: 'jpeg', quality: 0.98 },
              html2canvas: { scale: 3 },
              jsPDF: { unit: 'mm', format: [75, 140], orientation: 'portrait' }
            };
            html2pdf().set(opt).from(receiptElem).save().then(() => {
              receiptElem.style.display = 'none';
            });
          } else {
            window.print();
          }
        }

        function switchTab(t) {
          ['viewPos', 'viewProds', 'viewLedger', 'viewHistory'].forEach(id => document.getElementById(id).classList.add('hidden'));
          ['tabPos', 'tabProds', 'tabLedger', 'tabHistory'].forEach(id => document.getElementById(id).className = "tab-btn");
          if(t === 'pos') {
            document.getElementById('viewPos').classList.remove('hidden');
            document.getElementById('tabPos').className = "tab-btn active";
          } else if(t === 'prods') {
            document.getElementById('viewProds').classList.remove('hidden');
            document.getElementById('tabProds').className = "tab-btn active";
          } else if(t === 'ledger') {
            document.getElementById('viewLedger').classList.remove('hidden');
            document.getElementById('tabLedger').className = "tab-btn active";
          } else {
            document.getElementById('viewHistory').classList.remove('hidden');
            document.getElementById('tabHistory').className = "tab-btn active";
          }
        }

        /* PRODUCT LOGIC */
        async function saveProduct() {
          let code = document.getElementById('npCode').value.trim();
          let name = document.getElementById('npName').value.trim();
          let unit = document.getElementById('npUnit').value;
          let price = parseFloat(document.getElementById('npRate').value);
          if(!code || !name || isNaN(price)) return alert('விவரங்களை முழுமையாக உள்ளிடவும்!');
          await fetch('/api/product', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code, name, unit, price}) });
          clearProdForm();
          await fetchAll();
          alert('பொருள் சேமிக்கப்பட்டது!');
        }

        function clearProdForm() {
          document.getElementById('npCode').value = '';
          document.getElementById('npName').value = '';
          document.getElementById('npRate').value = '';
          document.getElementById('prodFormTitle').innerText = '➕ புதிய பொருள் / விலை திருத்தம்';
          document.getElementById('btnSaveProd').innerText = '💾 பொருள் சேமி';
          document.getElementById('prodEditBadge').classList.add('hidden');
        }

        function populateProdEdit(code, name, unit, price) {
          document.getElementById('npCode').value = code;
          document.getElementById('npName').value = name;
          document.getElementById('npUnit').value = unit || 'Kg';
          document.getElementById('npRate').value = price;
          document.getElementById('prodFormTitle').innerText = '✏️ விலை / பொருள் திருத்தம்:';
          document.getElementById('btnSaveProd').innerText = '💾 Update';
          document.getElementById('prodEditBadge').classList.remove('hidden');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        async function deleteProduct(code) {
          if(!confirm('இந்தப் பொருளை நீக்கவா?')) return;
          await fetch(`/api/product/${code}`, { method: 'DELETE' });
          clearProdForm();
          await fetchAll();
        }

        function renderProductList() {
          let h = '';
          db.products.forEach(p => {
            h += `<div style="display:flex; justify-content:space-between; align-items:center; background:#ffffff; padding:8px 10px; border-radius:8px; border:1px solid #e2e8f0; font-size:12px; font-weight:700;">
                    <div style="flex:1;">
                      <span style="color:#0f172a;">🏷️ [${p.code}] ${p.name} (${p.unit})</span>
                      <span style="color:#2563eb; margin-left:6px;">₹${p.price}</span>
                    </div>
                    <div style="display:flex; gap:4px;">
                      <button onclick="populateProdEdit('${p.code}', '${p.name}', '${p.unit}', ${p.price})" class="btn btn-soft-blue" style="padding:4px 8px; font-size:11px;">Edit</button>
                      <button onclick="deleteProduct('${p.code}')" class="btn btn-red" style="padding:4px 8px; font-size:11px;">நீக்கு</button>
                    </div>
                  </div>`;
          });
          document.getElementById('prodList').innerHTML = h;
        }

        /* CUSTOMER LOGIC */
        async function saveCustomer() {
          let id = parseInt(document.getElementById('ncId').value) || 0;
          let name = document.getElementById('ncName').value.trim();
          let balance = parseFloat(document.getElementById('ncBal').value) || 0;
          if(!name) return alert('பெயரை உள்ளிடவும்!');
          
          let res = await fetch('/api/customer', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({id, name, balance}) 
          });
          let out = await res.json();
          if(out.status === 'exists') alert(out.msg);
          else {
            clearCustForm();
            await fetchAll();
            alert(id > 0 ? 'வாடிக்கையாளர் விவரம் திருத்தப்பட்டது!' : 'வாடிக்கையாளர் கணக்கு சேமிக்கப்பட்டது!');
          }
        }

        function clearCustForm() {
          document.getElementById('ncId').value = "0";
          document.getElementById('ncName').value = '';
          document.getElementById('ncBal').value = '0';
          document.getElementById('custFormTitle').innerText = '➕ புதிய வாடிக்கையாளர் சேர்க்க:';
          document.getElementById('btnSaveCust').innerText = '💾 சேமி (Save)';
          document.getElementById('custEditBadge').classList.add('hidden');
        }

        function populateCustEdit(id, name, balance) {
          document.getElementById('ncId').value = id;
          document.getElementById('ncName').value = name;
          document.getElementById('ncBal').value = balance;
          document.getElementById('custFormTitle').innerText = '✏️ வாடிக்கையாளர் விவரம் திருத்தம்:';
          document.getElementById('btnSaveCust').innerText = '💾 Update';
          document.getElementById('custEditBadge').classList.remove('hidden');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        async function deleteCustomer(cid, name) {
          if(!confirm(`'${name}' வாடிக்கையாளரை நீக்கவா?`)) return;
          await fetch(`/api/customer/${cid}`, { method: 'DELETE' });
          clearCustForm();
          await fetchAll();
        }

        async function submitDirectPayment() {
          let cid = parseInt(document.getElementById('payCustSelect').value);
          let amount = parseFloat(document.getElementById('payAmount').value);
          if(!cid || isNaN(amount) || amount <= 0) return alert('சரியான வரவுத் தொகையை உள்ளிடவும்!');
          await fetch('/api/customer/payment', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: cid, amount: amount}) });
          document.getElementById('payAmount').value = '';
          await fetchAll();
          alert('வரவு வைக்கப்பட்டது!');
        }

        async function openPassbook(cid, name, bal) {
          currentOpenCust = { id: cid, name: name, balance: bal };
          document.getElementById('pbCustName').innerText = '🏨 ' + name;
          document.getElementById('pbCustBal').innerText = 'தற்போதைய பாக்கி: ₹' + parseFloat(bal).toFixed(2);
          document.getElementById('pbPrintCustInfo').innerText = `வாடிக்கையாளர்: ${name} | மொத்த பாக்கி: ₹${parseFloat(bal).toFixed(2)}`;
          
          let res = await fetch(`/api/customer/ledger/${cid}`);
          let out = await res.json();
          let rows = '';
          if(out.ledger.length === 0) {
            rows = '<tr><td colspan="5" class="text-center" style="padding:12px; color:#64748b;">பரிவர்த்தனைகள் இல்லை</td></tr>';
          } else {
            out.ledger.forEach(l => {
              rows += `<tr>
                <td style="color:#64748b; font-size:10px;">${l.txn_date}</td>
                <td><b>${l.description}</b></td>
                <td class="text-right" style="color:#dc2626; font-weight:800;">${l.debit > 0 ? '₹'+l.debit.toFixed(2) : '-'}</td>
                <td class="text-right" style="color:#16a34a; font-weight:800;">${l.credit > 0 ? '₹'+l.credit.toFixed(2) : '-'}</td>
                <td class="text-right" style="font-weight:900;">₹${l.balance.toFixed(2)}</td>
              </tr>`;
            });
          }
          document.getElementById('pbTableBody').innerHTML = rows;
          document.getElementById('passbookModal').classList.remove('hidden');
        }

        function closePassbook() {
          document.getElementById('passbookModal').classList.add('hidden');
        }

        function downloadPassbookPdf() {
          let printHeader = document.getElementById('pbHeaderPrint');
          printHeader.style.display = 'block';
          let element = document.getElementById('passbookPrintArea');
          
          let opt = {
            margin: 4,
            filename: `Passbook_${currentOpenCust.name}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2 },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
          };
          
          html2pdf().set(opt).from(element).save().then(() => {
            printHeader.style.display = 'none';
          });
        }

        function renderLedgerList() {
          let h = '';
          if(!db.customers || db.customers.length === 0) h = '<p style="font-size:12px; color:#64748b; text-align:center; padding:10px;">வாடிக்கையாளர்கள் இல்லை.</p>';
          else {
            db.customers.forEach(c => {
              h += `<div style="display:flex; justify-content:space-between; align-items:center; background:#ffffff; padding:8px 10px; border-radius:8px; border:1px solid #e2e8f0; font-size:12px; font-weight:700;">
                      <div onclick="openPassbook(${c.id}, '${c.name}', ${c.balance})" style="cursor:pointer; flex:1;">
                        <span style="color:#0f172a;">🏨 ${c.name}</span>
                        <span style="color:#dc2626; margin-left:4px;">பாக்கி: ₹${parseFloat(c.balance).toFixed(2)}</span>
                        <span style="font-size:10px; color:#2563eb; display:block; text-decoration:underline; margin-top:2px;">📖 பாஸ்புக் / PDF பார்</span>
                      </div>
                      <div style="display:flex; gap:4px;">
                        <button onclick="populateCustEdit(${c.id}, '${c.name}', ${c.balance})" class="btn btn-soft-blue" style="padding:4px 8px; font-size:11px;">Edit</button>
                        <button onclick="deleteCustomer(${c.id}, '${c.name}')" class="btn btn-red" style="padding:4px 8px; font-size:11px;">நீக்கு</button>
                      </div>
                    </div>`;
            });
          }
          document.getElementById('ledgerList').innerHTML = h;
        }

        function renderHistoryList() {
          let h = '';
          if(!db.bills || db.bills.length === 0) h = '<p style="font-size:12px; color:#64748b; text-align:center; padding:10px;">பில்கள் இல்லை.</p>';
          else {
            db.bills.forEach((b) => {
              h += `<div style="background:#ffffff; padding:10px; border-radius:8px; border:1px solid #e2e8f0; font-size:12px;">
                      <div style="display:flex; justify-content:space-between; font-weight:800;">
                        <span>பில் #${b.bill_no} (${b.customer_name})</span>
                        <span style="color:#2563eb;">₹${b.total.toFixed(2)}</span>
                      </div>
                      <div style="font-size:11px; color:#64748b; margin-top:3px;">${b.time_str}</div>
                      <div style="display:flex; gap:6px; margin-top:8px;">
                        <button onclick='generateOutput(${b.bill_no}, "${b.time_str}", "${b.customer_type}", "${b.customer_name}", ${JSON.stringify(b.items)}, ${b.total}, ${b.paid || 0}, false)' class="btn btn-blue" style="flex:1; padding:6px; font-size:11px;">🖨️ Print</button>
                        <button onclick='generateOutput(${b.bill_no}, "${b.time_str}", "${b.customer_type}", "${b.customer_name}", ${JSON.stringify(b.items)}, ${b.total}, ${b.paid || 0}, true)' class="btn btn-soft-amber" style="flex:1; padding:6px; font-size:11px;">📥 PDF</button>
                      </div>
                    </div>`;
            });
          }
          document.getElementById('billHistoryList').innerHTML = h;
        }
      </script>
    </body>
    </html>
    """