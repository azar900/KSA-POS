import os
import json
from datetime import datetime
import pytz
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()
IST = pytz.timezone('Asia/Kolkata')

RAW_DB_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(RAW_DB_URL and "YOUR_USER" not in RAW_DB_URL and RAW_DB_URL.startswith("postgres"))

if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        USE_POSTGRES = False

DB_FILE = "test_store.db"

def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(RAW_DB_URL)
    else:
        import sqlite3
        conn = sqlite3.connect(DB_FILE, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query, params=(), fetch_one=False, fetch_all=False, commit=False):
    conn = None
    try:
        conn = get_db()
        if USE_POSTGRES:
            c = conn.cursor(cursor_factory=RealDictCursor)  # type: ignore
            pg_query = query.replace("?", "%s")
            c.execute(pg_query, params)
            data = None
            if fetch_one:
                row = c.fetchone()
                data = dict(row) if row else None
            elif fetch_all:
                data = [dict(r) for r in c.fetchall()]
            if commit:
                conn.commit()
            c.close()
            return data
        else:
            c = conn.cursor()
            c.execute(query, params)
            data = None
            if fetch_one:
                row = c.fetchone()
                data = dict(row) if row else None
            elif fetch_all:
                data = [dict(r) for r in c.fetchall()]
            if commit:
                conn.commit()
            return data
    except Exception as e:
        if conn and commit:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def init_db():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        if USE_POSTGRES:
            c.execute("""CREATE TABLE IF NOT EXISTS products 
                         (code TEXT PRIMARY KEY, name TEXT, print_name TEXT, unit TEXT, price NUMERIC, category TEXT DEFAULT 'பொதுவானவை')""")
            try:
                c.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'பொதுவானவை'")
            except Exception:
                pass
            c.execute("""CREATE TABLE IF NOT EXISTS customers 
                         (id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, balance NUMERIC DEFAULT 0.0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS customer_ledger 
                         (id SERIAL PRIMARY KEY, customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE, 
                          txn_date TEXT, description TEXT, debit NUMERIC DEFAULT 0.0, credit NUMERIC DEFAULT 0.0, balance NUMERIC DEFAULT 0.0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS bills 
                         (id SERIAL PRIMARY KEY, bill_no INTEGER, bill_date_key TEXT, customer_type TEXT, 
                          customer_name TEXT, items TEXT, total NUMERIC, paid NUMERIC DEFAULT 0.0, time_str TEXT)""")
        else:
            c.execute("""CREATE TABLE IF NOT EXISTS products 
                         (code TEXT PRIMARY KEY, name TEXT, print_name TEXT, unit TEXT, price REAL, category TEXT DEFAULT 'பொதுவானவை')""")
            try:
                c.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'பொதுவானவை'")
            except Exception:
                pass
            c.execute("""CREATE TABLE IF NOT EXISTS customers 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, balance REAL DEFAULT 0.0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS customer_ledger 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, txn_date TEXT, description TEXT, 
                          debit REAL DEFAULT 0.0, credit REAL DEFAULT 0.0, balance REAL DEFAULT 0.0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS bills 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, bill_no INTEGER, bill_date_key TEXT, customer_type TEXT, 
                          customer_name TEXT, items TEXT, total REAL, paid REAL DEFAULT 0.0, time_str TEXT)""")
            
            sample_prods = [
                ('101', 'seeragam', 'சீரகம்', 'Kg', 600.0, 'மசாலா & வாசனைப் பொருட்கள்'),
                ('102', 'milagu', 'மிளகு', 'Kg', 900.0, 'மசாலா & வாசனைப் பொருட்கள்'),
                ('103', 'kadalai ennai', 'கடலை எண்ணெய்', 'L', 180.0, 'எண்ணெய் & நெய்'),
                ('104', 'jeeni', 'சீனி', 'Kg', 42.0, 'பேக்கிங் & இனிப்பு வகைகள்'),
                ('105', 'colgate paste', 'கோல்கேட் பேஸ்ட்', 'Pcs', 45.0, 'சோப்பு, பேஸ்ட் & பூஜா'),
                ('106', 'ponni arisi', 'பொன்னி அரிசி', 'Kg', 55.0, 'அரிசி & தானியங்கள்'),
                ('107', 'ponni arisi sippam', 'பொன்னி அரிசி (சிப்பம்)', 'Pcs', 1350.0, 'அரிசி & தானியங்கள்')
            ]
            for p in sample_prods:
                c.execute("INSERT OR IGNORE INTO products (code, name, print_name, unit, price, category) VALUES (?, ?, ?, ?, ?, ?)", p)

        # Smart Category Dictionary
        smart_categorizer = [
            ('எண்ணெய் & நெய்', ['%gold winner%', '%mr gold%', '%fortune%', '%sunland%', '%idayam%', '%udhai%', '%udhaya%', '%ghee%', '%oil%', '%ennai%', '%enna%', '%nallenna%', '%kadalenna%', '%thengaenna%', '%vilakkenna%', '%dalda%', '%vanaspathi%', '%நெய்%', '%எண்ணெய்%']),
            ('சோப்பு, பேஸ்ட் & பூஜா', ['%hamam%', '%cinthol%', '%lifebuoy%', '%lux%', '%santhoor%', '%pears%', '%medimix%', '%dettol%', '%soap%', '%colgate%', '%close up%', '%pepsodent%', '%sensodyne%', '%paste%', '%brush%', '%surf%', '%aerial%', '%tide%', '%rin%', '%wheel%', '%vim%', '%exo%', '%shampoo%', '%clinic plus%', '%vatika%', '%meera%', '%dhoop%', '%agarbathi%', '%oothabathi%', '%theepetti%', '%karpooram%', '%சோப்பு%', '%பேஸ்ட்%', '%ஊதுபத்தி%', '%கற்பூரம்%']),
            ('சிற்றுண்டி & பிஸ்கட்', ['%marie%', '%parle%', '%good day%', '%bourbon%', '%oreo%', '%monaco%', '%50-50%', '%milk bikis%', '%tiger%', '%biscuit%', '%biskut%', '%rusk%', '%cake%', '%munch%', '%kitkat%', '%dairy milk%', '%lays%', '%kurkure%', '%bingo%', '%chips%', '%mixture%', '%sev%', '%appalam%', '%vadagam%', '%maggi%', '%yippee%', '%noodles%', '%ரஸ்க்%', '%அப்பளம்%']),
            ('டீ, காபி & பானங்கள்', ['%3 roses%', '%taj mahal%', '%avt%', '%chakra gold%', '%kannan devan%', '%red label%', '%tea%', '%bru%', '%sunrise%', '%nescafe%', '%coffee%', '%boost%', '%horlicks%', '%complan%', '%bournvita%', '%bovonto%', '%7up%', '%mirinda%', '%coke%', '%pepsi%', '%டீ%', '%காபி%']),
            ('அரிசி & தானியங்கள்', ['%ponni%', '%baba%', '%nandhi%', '%delight%', '%bullet%', '%biryani%', '%basmati%', '%aashirvaad%', '%arisi%', '%rice%', '%wheat%', '%godhumai%', '%atta%', '%maida%', '%ravai%', '%sooji%', '%semiya%', '%kambu%', '%solam%', '%ragi%', '%கோதுமை%', '%ரவை%', '%மைதா%', '%அரிசி%']),
            ('பருப்பு வகைகள்', ['%thoor%', '%thuvaram%', '%channa%', '%kadalai%', '%moong%', '%paasi%', '%urad%', '%ulundu%', '%paruppu%', '%parupu%', '%dal%', '%dhal%', '%payaru%', '%pottukadalai%', '%sundal%', '%pattani%', '%rajma%', '%kollu%', '%பருப்பு%', '%உளுந்து%', '%கொண்டைக்கடலை%', '%பட்டாணி%']),
            ('பேக்கிங் & இனிப்பு வகைகள்', ['%seeni%', '%sakkarai%', '%sugar%', '%nattu sakkarai%', '%vellam%', '%karupatti%', '%kalkandu%', '%uppu%', '%salt%', '%tata salt%', '%puli%', '%poondu%', '%சீனி%', '%சர்க்கரை%', '%வெல்லம்%', '%உப்பு%', '%புளி%']),
            ('மசாலா & வாசனைப் பொருட்கள்', ['%seeragam%', '%jeeragam%', '%milagu%', '%kadugu%', '%sombu%', '%venthaiyam%', '%pattai%', '%krambu%', '%elakkai%', '%kasakasa%', '%sakthi%', '%aachi%', '%everest%', '%mdh%', '%masala%', '%sambhar%', '%rasam%', '%malli%', '%dhaniya%', '%manjal%', '%மஞ்சள்%', '%மிளகு%', '%சீரகம்%', '%கடுகு%', '%மசாலா%'])
        ]

        for cat_name, kw_list in smart_categorizer:
            for kw in kw_list:
                update_sql = f"UPDATE products SET category = %s WHERE (category = 'பொதுவானவை' OR category IS NULL) AND (LOWER(name) LIKE %s OR LOWER(print_name) LIKE %s)" if USE_POSTGRES else f"UPDATE products SET category = ? WHERE (category = 'பொதுவானவை' OR category IS NULL) AND (LOWER(name) LIKE ? OR LOWER(print_name) LIKE ?)"
                c.execute(update_sql, (cat_name, kw, kw))

        conn.commit()
        c.close()
    except Exception as e:
        if conn: conn.rollback()
        print("DB Init Info:", e)
    finally:
        if conn: conn.close()

init_db()

@app.get("/api/data")
def get_data():
    try:
        products = execute_query("SELECT code, name, COALESCE(print_name, name) as print_name, unit, price, COALESCE(category, 'பொதுவானவை') as category FROM products", fetch_all=True)
        # Sort in Python safely regardless of integer or text in DB
        def sort_key(p):
            try:
                return int(p['code'])
            except:
                return 999999
        products = sorted(products or [], key=sort_key)
        customers = execute_query("SELECT id, name, balance FROM customers ORDER BY name ASC", fetch_all=True)
        return {"status": "ok", "products": products, "customers": customers or []}
    except Exception as e:
        return {"status": "error", "msg": str(e), "products": [], "customers": []}

@app.get("/api/bills/by-date/{date_str}")
def get_bills_by_date(date_str: str):
    try:
        raw_bills = execute_query("""SELECT id, bill_no, bill_date_key, customer_type, customer_name, items, 
                                            total, paid, time_str 
                                     FROM bills WHERE bill_date_key=? ORDER BY bill_no DESC""", (date_str,), fetch_all=True)
        bills = []
        for r in (raw_bills or []):
            d = dict(r)
            if isinstance(d['items'], str):
                try:
                    d['items'] = json.loads(d['items'])
                except Exception:
                    d['items'] = []
            bills.append(d)
        return {"status": "ok", "bills": bills}
    except Exception as e:
        return {"status": "error", "msg": str(e), "bills": []}

@app.get("/api/customer/ledger/{cid}")
def get_customer_ledger(cid: int):
    try:
        ledger = execute_query("""SELECT txn_date, description, debit, credit, balance 
                                  FROM customer_ledger WHERE customer_id=? ORDER BY id DESC""", (cid,), fetch_all=True)
        return {"status": "ok", "ledger": ledger or []}
    except Exception as e:
        return {"status": "error", "msg": str(e), "ledger": []}

class ProductItem(BaseModel):
    code: str
    name: str
    print_name: str
    unit: str
    price: float
    category: str = "பொதுவானவை"

@app.post("/api/product")
def update_product(p: ProductItem):
    try:
        cat = p.category.strip() if p.category else "பொதுவானவை"
        clean_code = str(p.code).strip()
        clean_name = p.name.strip().lower()
        clean_print = p.print_name.strip().lower()

        # 1. டூப்ளிகேட் பெயர் சரிபார்ப்பு (Duplicate Name Check)
        chk_sql = """SELECT code, print_name FROM products 
                     WHERE (LOWER(name) = ? OR LOWER(print_name) = ? OR LOWER(name) = ? OR LOWER(print_name) = ?) 
                     AND CAST(code AS TEXT) != ?"""
        existing = execute_query(chk_sql, (clean_name, clean_name, clean_print, clean_print, clean_code), fetch_one=True)
        if existing:
            return {"status": "exists", "msg": f"'{existing['print_name']}' [கோட்: {existing['code']}] ஏற்கனவே கடையில் உள்ளது! ஒரே பொருளை இரண்டு முறை சேர்க்க முடியாது."}

        # 2. இன்சர்ட் அல்லது அப்டேட்
        if USE_POSTGRES:
            execute_query("""INSERT INTO products (code, name, print_name, unit, price, category) VALUES (?, ?, ?, ?, ?, ?)
                             ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name, print_name=EXCLUDED.print_name, unit=EXCLUDED.unit, price=EXCLUDED.price, category=EXCLUDED.category""",
                          (clean_code, p.name.strip(), p.print_name.strip(), p.unit, p.price, cat), commit=True)
        else:
            execute_query("""INSERT INTO products (code, name, print_name, unit, price, category) VALUES (?, ?, ?, ?, ?, ?)
                             ON CONFLICT(code) DO UPDATE SET name=excluded.name, print_name=excluded.print_name, unit=excluded.unit, price=excluded.price, category=excluded.category""",
                          (clean_code, p.name.strip(), p.print_name.strip(), p.unit, p.price, cat), commit=True)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

@app.delete("/api/product/{code}")
def delete_product(code: str):
    try:
        clean_code = str(code).strip()
        # PostgreSQL & SQLite இரண்டிற்கும் பாதுகாப்பான CAST(code AS TEXT)
        execute_query("DELETE FROM products WHERE CAST(code AS TEXT) = ?", (clean_code,), commit=True)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

class CustomerModel(BaseModel):
    id: int = 0
    name: str
    balance: float

@app.post("/api/customer")
def save_customer(cu: CustomerModel):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        now_str = datetime.now(IST).strftime("%d-%m-%Y %I:%M %p")
        c_name = cu.name.strip()
        
        check_q = "SELECT id FROM customers WHERE LOWER(name)=LOWER(%s)" if USE_POSTGRES else "SELECT id FROM customers WHERE LOWER(name)=LOWER(?)"
        c.execute(check_q, (c_name,))
        if c.fetchone():
            return {"status": "exists", "msg": f"'{c_name}' பெயரில் ஏற்கெனவே கணக்கு உள்ளது!"}
        
        if USE_POSTGRES:
            c.execute("INSERT INTO customers (name, balance) VALUES (%s, %s) RETURNING id", (c_name, cu.balance))
            row = c.fetchone()
            new_cid = row[0] if row else 0
            c.execute("""INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) 
                         VALUES (%s, %s, %s, %s, %s, %s)""", (new_cid, now_str, "தொடக்க இருப்பு", cu.balance, 0.0, cu.balance))
        else:
            c.execute("INSERT INTO customers (name, balance) VALUES (?, ?)", (c_name, cu.balance))
            new_cid = c.lastrowid
            c.execute("""INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) 
                         VALUES (?, ?, ?, ?, ?, ?)""", (new_cid, now_str, "தொடக்க இருப்பு", cu.balance, 0.0, cu.balance))
        
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "msg": str(e)}
    finally:
        if conn: conn.close()

@app.delete("/api/customer/{cid}")
def delete_customer(cid: int):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        param = "%s" if USE_POSTGRES else "?"
        c.execute(f"DELETE FROM customer_ledger WHERE customer_id={param}", (cid,))
        c.execute(f"DELETE FROM customers WHERE id={param}", (cid,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "msg": str(e)}
    finally:
        if conn: conn.close()

class PaymentModel(BaseModel):
    customer_id: int
    amount: float

@app.post("/api/customer/payment")
def add_payment(p: PaymentModel):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        param = "%s" if USE_POSTGRES else "?"
        c.execute(f"SELECT balance FROM customers WHERE id={param}", (p.customer_id,))
        row = c.fetchone()
        if row:
            cur_bal = float(row[0])
            new_bal = cur_bal - p.amount
            now_str = datetime.now(IST).strftime("%d-%m-%Y %I:%M %p")
            
            c.execute(f"UPDATE customers SET balance={param} WHERE id={param}", (new_bal, p.customer_id))
            c.execute(f"""INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance) 
                         VALUES ({param}, {param}, {param}, {param}, {param}, {param})""", 
                      (p.customer_id, now_str, "ரொக்க வரவு", 0.0, p.amount, new_bal))
            conn.commit()
            return {"status": "ok"}
        return {"status": "error", "msg": "வாடிக்கையாளர் கிடைக்கவில்லை"}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "msg": str(e)}
    finally:
        if conn: conn.close()

class BillRequest(BaseModel):
    customer_type: str
    customer_name: str
    items: list
    total: float
    paid: float

@app.post("/api/bill")
def save_bill(b: BillRequest):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        now_ist = datetime.now(IST)
        date_key = now_ist.strftime("%Y-%m-%d")
        time_str = now_ist.strftime("%d-%m-%Y %I:%M %p")
        param = "%s" if USE_POSTGRES else "?"
        
        if USE_POSTGRES:
            c.execute("SELECT pg_advisory_xact_lock(42);")
        else:
            c.execute("BEGIN IMMEDIATE")
            
        c.execute(f"SELECT MAX(bill_no) FROM bills WHERE bill_date_key={param}", (date_key,))
        row = c.fetchone()
        max_val = row[0] if (row and row[0] is not None) else None
        daily_bill_no = (max_val + 1) if max_val is not None else 1
        items_json = json.dumps(b.items, ensure_ascii=False)
        
        c.execute(f"""INSERT INTO bills (bill_no, bill_date_key, customer_type, customer_name, items, total, paid, time_str)
                     VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})""",
                  (daily_bill_no, date_key, b.customer_type, b.customer_name, items_json, b.total, b.paid, time_str))
        
        if b.customer_type == "ரெகுலர் கஸ்டமர் (Credit)" and b.customer_name:
            c.execute(f"SELECT id, balance FROM customers WHERE LOWER(name)=LOWER({param})", (b.customer_name.strip(),))
            cust_row = c.fetchone()
            if cust_row:
                cid = cust_row[0]
                old_bal = float(cust_row[1])
                net_add = b.total - b.paid
                new_bal = old_bal + net_add
                
                c.execute(f"UPDATE customers SET balance={param} WHERE id={param}", (new_bal, cid))
                c.execute(f"""INSERT INTO customer_ledger (customer_id, txn_date, description, debit, credit, balance)
                             VALUES ({param}, {param}, {param}, {param}, {param}, {param})""", 
                          (cid, time_str, f"பில் எண் #{daily_bill_no}", b.total, b.paid, new_bal))
                
        conn.commit()
        return {"status": "ok", "bill_no": daily_bill_no, "date_key": date_key, "time": time_str}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "msg": str(e)}
    finally:
        if conn: conn.close()

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
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background: #f1f5f9; color: #0f172a; padding: 4px; display: flex; justify-content: center; }
        .app-container { width: 100%; max-width: 500px; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.06); min-height: 98vh; display: flex; flex-direction: column; }
        
        .header { background: #1e3a8a; color: #ffffff; padding: 10px; text-align: center; }
        .header h1 { font-size: 1.15rem; font-weight: 800; letter-spacing: 0.5px; }
        .header p { font-size: 11px; color: #93c5fd; }
        
        .nav-tabs { display: flex; background: #e2e8f0; padding: 3px; gap: 3px; }
        .tab-btn { flex: 1; padding: 11px 2px; border: none; background: transparent; font-size: 12px; font-weight: 700; border-radius: 6px; cursor: pointer; color: #475569; min-height: 44px; }
        .tab-btn.active { background: #ffffff; color: #1e3a8a; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        
        .view-panel { padding: 10px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .hidden { display: none !important; }
        
        .box { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px; position: relative; }
        .input-group { display: flex; gap: 5px; margin-bottom: 5px; }
        input, select { width: 100%; padding: 10px 8px; border: 1px solid #94a3b8; border-radius: 6px; font-size: 14px; font-weight: 600; outline: none; background: #ffffff; color: #0f172a; height: 42px; }
        input:focus, select:focus { border-color: #2563eb; ring: 1px solid #2563eb; }
        
        .btn { padding: 10px; border: none; border-radius: 6px; font-weight: 700; font-size: 13px; cursor: pointer; text-align: center; min-height: 42px; display: flex; align-items: center; justify-content: center; }
        .btn-blue { background: #2563eb; color: #ffffff; }
        .btn-soft-blue { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
        .btn-green { background: #16a34a; color: #ffffff; }
        .btn-amber { background: #d97706; color: #ffffff; }
        .btn-soft-amber { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
        .btn-red { background: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; }
        
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 8px 4px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f8fafc; font-weight: 800; color: #334155; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        
        .total-box { background: #0f172a; color: #ffffff; padding: 10px 12px; border-radius: 8px; }
        .suggest-box { position: absolute; top: 52px; left: 8px; right: 8px; background: #ffffff; border: 1px solid #94a3b8; border-radius: 6px; max-height: 180px; overflow-y: auto; z-index: 50; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .suggest-item { padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; }
        .suggest-item:hover, .suggest-item:active { background: #eff6ff; color: #2563eb; }
        
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; padding: 8px; z-index: 100; }
        .modal-card { background: #ffffff; border-radius: 10px; max-width: 440px; width: 100%; max-height: 90vh; display: flex; flex-direction: column; padding: 12px; overflow: hidden; }

        @media print {
          body * { visibility: hidden; }
          #receipt, #receipt * { visibility: visible; }
          #receipt { 
            position: absolute; 
            left: 0; 
            top: 0; 
            width: 72mm !important; 
            margin: 0 !important;
            padding: 2px 4px !important;
            font-family: 'Courier New', Courier, monospace !important; 
            font-size: 12px !important; 
            font-weight: normal !important; 
            color: #000000 !important; 
            line-height: 1.3 !important; 
            display: block !important; 
          }
          #receipt table { width: 100% !important; table-layout: fixed; border-collapse: collapse; margin: 3px 0; }
          #receipt th { 
            background: transparent !important; 
            color: #000000 !important; 
            font-weight: bold !important; 
            font-size: 12px !important; 
            padding: 2px 0 !important;
            border-bottom: 1px dashed #000000 !important;
          }
          #receipt td { 
            color: #000000 !important; 
            font-weight: normal !important; 
            font-size: 12px !important; 
            padding: 3px 0 !important;
            border-bottom: 0.5px dotted #777777 !important;
            word-break: break-word;
          }
          #receipt .col-item { width: 50%; text-align: left; }
          #receipt .col-qty  { width: 22%; text-align: center; }
          #receipt .col-amt  { width: 28%; text-align: right; }
          #receipt .border-b { border-bottom: 1px dashed #000000 !important; margin: 4px 0 !important; }
        }
      </style>
    </head>
    <body>
      <div class="app-container">
        <div class="header">
          <h1>🏪 KSA மளிகை, திருமயம்</h1>
          <p>அதிவேக மொபைல் பில்லிங் & கணக்கு முறை</p>
        </div>

        <div class="nav-tabs">
          <button onclick="switchTab('pos')" id="tabPos" class="tab-btn active">🛒 பில்லிங்</button>
          <button onclick="switchTab('prods')" id="tabProds" class="tab-btn">🏷️ பொருட்கள்</button>
          <button onclick="switchTab('ledger')" id="tabLedger" class="tab-btn">📒 கஸ்டமர்</button>
          <button onclick="switchTab('history')" id="tabHistory" class="tab-btn">📜 ஹிஸ்டரி</button>
        </div>

        <!-- 1. POS TAB -->
        <div id="viewPos" class="view-panel">
          <div class="box" style="background: #eff6ff; border-color: #bfdbfe;">
            <div class="input-group" style="margin-bottom: 0;">
              <select id="custType" onchange="onCustTypeChange()" style="flex: 1.1;">
                <option value="வாடிக்கையாளர் (Cash)">வாடிக்கையாளர் (ரொக்கம்)</option>
                <option value="ரெகுலர் கஸ்டமர் (Credit)">ரெகுலர் கஸ்டமர் (Credit)</option>
              </select>
              <input type="text" id="cashCustNameInput" placeholder="பெயர் (mani, kumar...)" style="flex: 1;" oninput="onCashCustTanglishType(this.value)">
            </div>

            <div id="regularCustDiv" class="hidden" style="margin-top: 5px;">
              <select id="regularCustSelect" onchange="updatePosCustInfo()"></select>
              <div id="posCustBalBadge" style="font-size: 12px; font-weight: 800; color: #1e40af; margin-top: 3px;"></div>
            </div>
          </div>

          <div class="box">
            <div class="input-group">
              <input type="text" id="posCode" placeholder="Code" style="flex: 0.8; text-align: center; font-size: 15px; font-weight: 800;" oninput="onPosCodeInput()">
              <input type="text" id="posSearch" placeholder="🔍 தேடல் (seeragam, ponni...)" style="flex: 2.2;" oninput="handlePosSmartSearch(this.value)" autocomplete="off">
            </div>

            <div id="posSuggestions" class="suggest-box hidden"></div>

            <div class="input-group">
              <input type="text" id="posTamilName" placeholder="பொருள் பெயர்" style="flex: 2; font-weight: 700; color: #166534; background: #f0fdf4;" readonly>
              <input type="text" id="posUnitTag" placeholder="Unit" style="flex: 1; text-align: center; background: #f1f5f9; font-weight: 700; color: #475569;" readonly>
            </div>

            <div class="input-group">
              <input type="text" id="posQty" placeholder="அளவு (எ.கா: 25, 450, 50g)" style="flex: 1.2; text-align: center; font-size: 15px;" oninput="recalcSmartTotal()">
              <input type="number" id="posRate" placeholder="விலை ₹" style="flex: 1;" oninput="recalcSmartTotal()">
              <input type="number" id="posTotal" placeholder="தொகை ₹" style="flex: 1.1; text-align: right; background: #fef9c3; font-weight: 800; color: #854d0e;" readonly>
            </div>

            <button onclick="addToBill()" class="btn btn-green" style="width: 100%; margin-top: 2px;">➕ பில்லில் சேர் (Add Item)</button>
          </div>

          <div style="border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; max-height: 200px; overflow-y: auto;">
            <table>
              <thead>
                <tr>
                  <th style="color: #000; font-weight: 800;">பொருள்</th>
                  <th class="text-center" style="color: #000; font-weight: 800;">அளவு</th>
                  <th class="text-right" style="color: #000; font-weight: 800;">தொகை (₹)</th>
                  <th class="text-center" style="width: 32px;"></th>
                </tr>
              </thead>
              <tbody id="cartTable"></tbody>
            </table>
          </div>

          <div class="total-box">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; color: #cbd5e1;">பில் மொத்தம்:</span>
              <span style="font-size: 1.35rem; font-weight: 900; color: #facc15;">₹<span id="billTotal">0.00</span></span>
            </div>
            
            <div id="regularPaidRow" class="hidden" style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px; padding-top: 6px; border-top: 1px solid #334155;">
              <span style="font-size: 12px; color: #4ade80; font-weight: 700;">வரவு (Advance):</span>
              <input type="number" id="billPaidAmt" value="0" style="width: 100px; text-align: right; padding: 4px; background: #0f172a; color: #ffffff; border: 1px solid #475569; border-radius: 4px; height: 34px;">
            </div>
          </div>

          <div style="display: flex; gap: 6px;">
            <button onclick="completeBill(false)" class="btn btn-blue" style="flex: 1.2;">🖨️ பிரிண்ட்</button>
            <button onclick="completeBill(true)" class="btn btn-soft-amber" style="flex: 0.8;">📥 PDF</button>
          </div>
        </div>

        <!-- 2. PRODUCTS TAB (DUPLICATE PROTECTED + BULLETPROOF DELETE) -->
        <div id="viewProds" class="view-panel hidden">
          <div class="box" style="background: #f0fdf4; border-color: #bbf7d0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
              <span id="prodFormTitle" style="font-size: 12px; font-weight: 800; color: #166534;">➕ புதிய பொருள் சேர்த்தல்</span>
              <span id="prodEditBadge" class="hidden" style="font-size: 10px; background: #bbf7d0; padding: 2px 5px; border-radius: 4px; font-weight: 800; color: #166534;">Editing</span>
            </div>
            
            <div class="input-group">
              <input type="text" id="npCode" placeholder="Code" style="flex: 0.8; text-align: center; font-weight: 800; background: #e2e8f0;" readonly>
              <input type="text" id="npName" placeholder="Tanglish பெயர் (gold winner, thoor...)" style="flex: 2.2;" oninput="onTanglishType(this.value)">
            </div>
            
            <div class="input-group">
              <input type="text" id="npPrintName" placeholder="தமிழ் பெயர்" style="flex: 2; font-weight: 700; color: #166534;">
              <select id="npUnit" style="flex: 1;">
                <option value="Kg">கிலோ (Kg)</option>
                <option value="L">லிட்டர் (L)</option>
                <option value="Pcs">எண்ணிக்கை (Pcs)</option>
              </select>
            </div>
            
            <div class="input-group">
              <select id="npCategory" style="flex: 1.6; font-size: 13px;">
                <option value="அரிசி & தானியங்கள்">🌾 அரிசி & தானியங்கள்</option>
                <option value="பருப்பு வகைகள்">🫘 பருப்பு வகைகள்</option>
                <option value="எண்ணெய் & நெய்">🛢️ எண்ணெய் & நெய்</option>
                <option value="மசாலா & வாசனைப் பொருட்கள்">🌶️ மசாலா & வாசனைப் பொருட்கள்</option>
                <option value="பேக்கிங் & இனிப்பு வகைகள்">🍬 பேக்கிங் & இனிப்பு வகைகள்</option>
                <option value="சிற்றுண்டி & பிஸ்கட்">🍪 சிற்றுண்டி & பிஸ்கட்</option>
                <option value="டீ, காபி & பானங்கள்">☕ டீ, காபி & பானங்கள்</option>
                <option value="சோப்பு, பேஸ்ட் & பூஜா">🧼 சோப்பு, பேஸ்ட் & பூஜா</option>
                <option value="பொதுவானவை">📦 பொதுவானவை</option>
              </select>
              <input type="number" id="npRate" placeholder="விலை ₹" style="flex: 1; font-weight: 700;">
            </div>
            
            <div style="display: flex; gap: 5px; margin-top: 3px;">
              <button onclick="saveProduct()" id="btnSaveProd" class="btn btn-green" style="flex: 1;">💾 சேமி</button>
              <button onclick="clearProdForm()" class="btn" style="background: #e2e8f0;">Clear</button>
            </div>
          </div>

          <div class="box" style="padding: 6px;">
            <div class="input-group" style="margin-bottom: 5px;">
              <select id="catFilterSelect" onchange="resetAndFilterProducts()" style="font-size: 13px; font-weight: 700; background: #f8fafc; border-color: #3b82f6; color: #1e40af;">
                <option value="ALL">📁 அனைத்துப் பிரிவுகளும் (All)</option>
                <option value="அரிசி & தானியங்கள்">🌾 அரிசி & தானியங்கள்</option>
                <option value="பருப்பு வகைகள்">🫘 பருப்பு வகைகள்</option>
                <option value="எண்ணெய் & நெய்">🛢️ எண்ணெய் & நெய்</option>
                <option value="மசாலா & வாசனைப் பொருட்கள்">🌶️ மசாலா & வாசனைப் பொருட்கள்</option>
                <option value="பேக்கிங் & இனிப்பு வகைகள்">🍬 பேக்கிங் & இனிப்பு வகைகள்</option>
                <option value="சிற்றுண்டி & பிஸ்கட்">🍪 சிற்றுண்டி & பிஸ்கட்</option>
                <option value="டீ, காபி & பானங்கள்">☕ டீ, காபி & பானங்கள்</option>
                <option value="சோப்பு, பேஸ்ட் & பூஜா">🧼 சோப்பு, பேஸ்ட் & பூஜா</option>
                <option value="பொதுவானவை">📦 பொதுவானவை</option>
              </select>
            </div>
            <input type="text" id="prodSearchInput" placeholder="🔍 பெயர் அல்லது கோட் தேட..." oninput="resetAndFilterProducts()">
          </div>

          <div id="prodList" onscroll="onProdListScroll(this)" style="display: flex; flex-direction: column; gap: 5px; max-height: 290px; overflow-y: auto; padding-bottom: 10px;"></div>
        </div>

        <!-- 3. CUSTOMER LEDGER TAB -->
        <div id="viewLedger" class="view-panel hidden">
          <div class="box" style="background: #fffbeb; border-color: #fde68a;">
            <div style="font-size: 12px; font-weight: 800; color: #92400e; margin-bottom: 5px;">➕ புதிய வாடிக்கையாளர்</div>
            
            <div class="input-group">
              <input type="text" id="ncTanglishName" placeholder="🔍 Tanglish பெயர் (anbu, kannan...)" oninput="onCustomerTanglishType(this.value)">
            </div>
            
            <div class="input-group">
              <input type="text" id="ncName" placeholder="தமிழ் பெயர்" style="flex: 2; font-weight: 700; color: #1e3a8a;">
              <input type="number" id="ncBal" placeholder="தொடக்க இருப்பு ₹" value="0" style="flex: 1.1;">
            </div>
            <button onclick="saveCustomer()" id="btnSaveCust" class="btn btn-amber" style="width: 100%; margin-top: 2px;">💾 வாடிக்கையாளர் சேமி</button>
          </div>

          <div class="box" style="background: #f0fdf4; border-color: #bbf7d0;">
            <span style="font-size: 11px; font-weight: 700; color: #166534;">💵 ரொக்க வரவு சேர்க்க:</span>
            <div class="input-group" style="margin-top: 5px;">
              <select id="payCustSelect" style="flex: 1.6;"></select>
              <input type="number" id="payAmount" placeholder="வரவு ₹" style="flex: 1;">
            </div>
            <button onclick="submitDirectPayment()" class="btn btn-green" style="width: 100%; margin-top: 2px;">✅ வரவு ஏற்று</button>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h4 style="font-size: 12px; color: #475569;">வாடிக்கையாளர்கள்:</h4>
            <span style="font-size: 11px; color: #64748b;" id="custCountBadge">மொத்தம்: 0</span>
          </div>
          
          <div id="ledgerList" style="display: flex; flex-direction: column; gap: 5px; max-height: 260px; overflow-y: auto;"></div>

          <!-- Passbook Modal -->
          <div id="passbookModal" class="modal-overlay hidden">
            <div class="modal-card">
              <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                <div>
                  <h3 id="pbCustName" style="font-size: 14px; font-weight: 800; color: #1e3a8a;"></h3>
                  <p id="pbCustBal" style="font-size: 12px; font-weight: 800; color: #1e40af; margin-top: 1px;"></p>
                </div>
                <button onclick="closePassbook()" class="btn btn-red" style="padding: 2px 8px; font-size: 12px; min-height: 30px;">✕ மூடு</button>
              </div>

              <div style="display: flex; gap: 5px; margin: 8px 0;">
                <button onclick="window.print()" class="btn btn-blue" style="flex: 1; padding: 6px; font-size: 12px; min-height: 34px;">🖨️ பிரிண்ட்</button>
                <button onclick="downloadPassbookPdf()" class="btn btn-soft-amber" style="flex: 1; padding: 6px; font-size: 12px; min-height: 34px;">📥 A4 PDF</button>
              </div>

              <div id="passbookPrintArea" style="overflow-y: auto; flex: 1;">
                <div id="pbHeaderPrint" style="text-align: center; border-bottom: 1px dashed #000; padding-bottom: 4px; margin-bottom: 6px;">
                  <h2 style="font-size: 15px; font-weight: 800; color:#000;">KSA மளிகை, திருமயம்</h2>
                  <div style="font-size: 11px; margin-top: 1px; color:#000;">வாடிக்கையாளர் கணக்கு அறிக்கை</div>
                  <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 3px; font-weight: 700; color:#000;">
                    <span id="pbPrintCustName"></span>
                    <span id="pbPrintCustBal"></span>
                  </div>
                </div>

                <table>
                  <thead>
                    <tr style="border-bottom: 1px solid #000;">
                      <th style="font-size: 11px; color:#000 !important; background:transparent !important;">தேதி</th>
                      <th style="font-size: 11px; color:#000 !important; background:transparent !important;">விவரம்</th>
                      <th class="text-right" style="font-size: 11px; color:#000 !important; background:transparent !important;">Dr</th>
                      <th class="text-right" style="font-size: 11px; color:#000 !important; background:transparent !important;">Cr</th>
                      <th class="text-right" style="font-size: 11px; color:#000 !important; background:transparent !important;">இருப்பு</th>
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
          <div class="box" style="background: #eff6ff; border-color: #bfdbfe; padding: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
              <span style="font-size: 12px; font-weight: 800; color: #1e40af;">📅 தேதி:</span>
              <input type="date" id="historyDatePicker" style="flex: 1; padding: 4px 8px; font-size: 13px; height: 36px;" onchange="loadHistoryByDate(this.value)">
              <button onclick="loadHistoryByDate(document.getElementById('historyDatePicker').value)" class="btn btn-soft-blue" style="padding: 4px 10px; min-height: 36px;" title="புதுப்பி">🔄</button>
            </div>
            <div style="margin-top: 5px;">
              <input type="text" id="historySearchInput" placeholder="🔍 பில் எண் அல்லது பெயர் தேட..." oninput="filterHistoryList(this.value)" style="height: 36px; font-size: 13px;">
            </div>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: #f1f5f9; padding: 6px 10px; border-radius: 6px;">
            <span style="font-size: 12px; font-weight: 800; color: #334155;" id="histCountLabel">பில்கள்: 0</span>
          </div>

          <div id="billHistoryList" style="display: flex; flex-direction: column; gap: 6px; max-height: 340px; overflow-y: auto;"></div>
        </div>
      </div>

      <!-- Bill Items Preview Modal -->
      <div id="billPreviewModal" class="modal-overlay hidden">
        <div class="modal-card">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
            <div>
              <h3 id="prevBillTitle" style="font-size: 14px; font-weight: 800; color: #1e3a8a;"></h3>
              <p id="prevBillTime" style="font-size: 11px; color: #64748b; margin-top: 1px;"></p>
            </div>
            <button onclick="closeBillPreview()" class="btn btn-red" style="padding: 2px 8px; font-size: 12px; min-height: 30px;">✕ மூடு</button>
          </div>

          <div style="margin: 8px 0; overflow-y: auto; flex: 1;">
            <table>
              <thead>
                <tr style="border-bottom: 1.5px solid #000;">
                  <th>பொருள்</th>
                  <th class="text-center">அளவு</th>
                  <th class="text-right">தொகை</th>
                </tr>
              </thead>
              <tbody id="prevBillItemsBody"></tbody>
            </table>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: #f8fafc; padding: 8px; border-radius: 6px; border: 1px solid #cbd5e1; margin-bottom: 8px;">
            <span style="font-size: 12px; font-weight: 700;">மொத்தம்:</span>
            <span style="font-size: 15px; font-weight: 900; color: #2563eb;" id="prevBillTotalVal"></span>
          </div>

          <div style="display: flex; gap: 6px;">
            <button id="prevBtnPrint" class="btn btn-blue" style="flex: 1.2;">🖨️ பிரிண்ட் எடு (Print)</button>
            <button id="prevBtnPdf" class="btn btn-soft-amber" style="flex: 0.8;">📥 PDF</button>
          </div>
        </div>
      </div>

      <!-- Thermal Receipt -->
      <div id="receipt" style="display: none; background: #ffffff; padding: 2px 4px; width: 72mm; color: #000000;">
        <div style="text-align: center; font-size: 15px; font-weight: bold; color: #000000; letter-spacing: 0.5px;">KSA மளிகை, திருமயம்</div>
        <div class="border-b"></div>
        <div style="display: flex; justify-content: space-between; font-size: 11.5px;"><span>பில் எண்: <span id="rBillNo"></span></span></div>
        <div style="display: flex; justify-content: space-between; font-size: 11px;"><span>தேதி: <span id="rTime"></span></span></div>
        <div style="font-size: 11.5px; margin-top: 1px;">கஸ்டமர்: <span id="rCust"></span></div>
        <div class="border-b"></div>
        <table>
          <thead>
            <tr>
              <th class="col-item">பொருள்</th>
              <th class="col-qty">அளவு</th>
              <th class="col-amt">தொகை</th>
            </tr>
          </thead>
          <tbody id="rItems"></tbody>
        </table>
        <div class="border-b"></div>
        <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: bold; color: #000000;">
          <span>மொத்தம்:</span><span>₹<span id="rTotal"></span></span>
        </div>
        <div id="rPaidRow" style="display: flex; justify-content: space-between; font-size: 11.5px; color: #000000;">
          <span>வரவு (Paid):</span><span>₹<span id="rPaid"></span></span>
        </div>
        <div class="border-b"></div>
        <div style="text-align: center; font-size: 10.5px; margin-top: 2px; color: #000000;">நன்றி! மீண்டும் வருக!</div>
      </div>

      <script>
        let db = { products: [], customers: [] };
        let currentDayBills = [];
        let cart = [];
        let activeBaseUnit = 'Kg';
        let currentSelectedProd = null;
        let transliterateTimer = null;
        let custTransliterateTimer = null;
        let cashCustTransliterateTimer = null;
        let posSearchTransliterateTimer = null;
        let activePbCustomer = null;

        let filteredProductsList = [];
        let prodDisplayLimit = 20;

        function getTodayDateStr() {
          let now = new Date();
          let y = now.getFullYear();
          let m = String(now.getMonth() + 1).padStart(2, '0');
          let d = String(now.getDate()).padStart(2, '0');
          return `${y}-${m}-${d}`;
        }

        async function fetchAll() {
          try {
            let res = await fetch('/api/data');
            let data = await res.json();
            if (data.status === 'ok') {
              db.products = data.products || [];
              db.customers = data.customers || [];
              document.getElementById('custCountBadge').innerText = 'மொத்தம்: ' + db.customers.length;
              setNextProductCode();
              resetAndFilterProducts();
              renderCustomerDropdowns();
              renderLedgerList();
            }
          } catch(e) { console.error("Data Load Error:", e); }
        }

        document.getElementById('historyDatePicker').value = getTodayDateStr();
        fetchAll();

        /* ==================== POS / BILLING ==================== */
        function onCashCustTanglishType(val) {
          clearTimeout(cashCustTransliterateTimer);
          let trimmed = val.trim();
          if (!trimmed) return;

          cashCustTransliterateTimer = setTimeout(async () => {
            try {
              let url = `https://inputtools.google.com/request?text=${encodeURIComponent(trimmed)}&itc=ta-t-i0-und&num=1`;
              let res = await fetch(url);
              let data = await res.json();
              if (data && data[0] === 'SUCCESS' && data[1][0][1].length > 0) {
                document.getElementById('cashCustNameInput').value = data[1][0][1][0];
              }
            } catch(err) {}
          }, 250);
        }

        function onPosCodeInput() {
          let codeVal = document.getElementById('posCode').value.trim();
          if (!codeVal) return;
          let p = db.products.find(x => String(x.code) === codeVal);
          if (p) selectPosProduct(p);
        }

        function handlePosSmartSearch(val) {
          let q = val.trim().toLowerCase();
          let suggestBox = document.getElementById('posSuggestions');
          if (!q) {
            suggestBox.classList.add('hidden');
            return;
          }
          
          showPosMatchingResults(q, '');

          clearTimeout(posSearchTransliterateTimer);
          posSearchTransliterateTimer = setTimeout(async () => {
            try {
              let url = `https://inputtools.google.com/request?text=${encodeURIComponent(q)}&itc=ta-t-i0-und&num=1`;
              let res = await fetch(url);
              let data = await res.json();
              if (data && data[0] === 'SUCCESS' && data[1][0][1].length > 0) {
                let tamilWord = data[1][0][1][0];
                showPosMatchingResults(q, tamilWord);
              }
            } catch(e) {}
          }, 200);
        }

        function showPosMatchingResults(engQ, tamilQ) {
          let suggestBox = document.getElementById('posSuggestions');
          let matched = db.products.filter(p => {
            let pCode = String(p.code);
            let pName = p.name.toLowerCase();
            let pPrint = p.print_name.toLowerCase();
            return pCode.includes(engQ) || pName.includes(engQ) || pPrint.includes(engQ) || (tamilQ && pPrint.includes(tamilQ));
          });

          if (matched.length === 0) {
            suggestBox.classList.add('hidden');
            return;
          }
          let h = '';
          matched.slice(0, 8).forEach(p => {
            h += `<div class="suggest-item" onclick="choosePosItem('${p.code}')">
                    <span><b>[${p.code}] ${p.print_name}</b> <small style="color:#64748b;">(${p.name})</small></span>
                    <span style="color:#2563eb;">₹${p.price}/${p.unit}</span>
                  </div>`;
          });
          suggestBox.innerHTML = h;
          suggestBox.classList.remove('hidden');
        }

        function choosePosItem(code) {
          let p = db.products.find(x => String(x.code) === String(code));
          if (p) selectPosProduct(p);
          document.getElementById('posSuggestions').classList.add('hidden');
        }

        function selectPosProduct(p) {
          currentSelectedProd = p;
          document.getElementById('posCode').value = p.code;
          document.getElementById('posSearch').value = p.print_name;
          document.getElementById('posTamilName').value = p.print_name;
          document.getElementById('posRate').value = p.price;
          activeBaseUnit = p.unit || 'Kg';
          document.getElementById('posUnitTag').value = activeBaseUnit;

          document.getElementById('posQty').value = '1';
          recalcSmartTotal();
          document.getElementById('posQty').focus();
        }

        function parseSmartInput(raw) {
          let str = String(raw).trim().toLowerCase();
          if (!str) return { qty: 0, isGram: false };

          if (str.includes('g') || str.includes('ml')) {
            let n = parseFloat(str.replace(/[^0-9.]/g, '')) || 0;
            return { qty: n, isGram: true };
          }
          let n = parseFloat(str) || 0;
          if (activeBaseUnit === 'Pcs') {
            return { qty: n, isGram: false };
          }
          if (n >= 100) {
            return { qty: n, isGram: true };
          }
          return { qty: n, isGram: false };
        }

        function recalcSmartTotal() {
          let rate = parseFloat(document.getElementById('posRate').value) || 0;
          let raw = document.getElementById('posQty').value;
          let parsed = parseSmartInput(raw);
          let tot = 0;

          if (activeBaseUnit === 'Pcs') {
            tot = parsed.qty * rate;
          } else {
            if (parsed.isGram) {
              tot = (parsed.qty / 1000) * rate;
            } else {
              tot = parsed.qty * rate;
            }
          }
          document.getElementById('posTotal').value = Math.round(tot);
        }

        function addToBill() {
          let tName = document.getElementById('posTamilName').value.trim();
          let raw = document.getElementById('posQty').value;
          let parsed = parseSmartInput(raw);
          let tot = parseFloat(document.getElementById('posTotal').value);

          if (!tName || parsed.qty <= 0 || isNaN(tot)) return alert('பொருள் மற்றும் சரியான அளவை உள்ளிடவும்!');

          let displayQty = '';
          if (activeBaseUnit === 'Pcs') {
            displayQty = `${parsed.qty} Pcs`;
          } else {
            if (parsed.isGram) {
              displayQty = `${parsed.qty} ${activeBaseUnit === 'Kg' ? 'g' : 'ml'}`;
            } else {
              displayQty = `${parsed.qty} ${activeBaseUnit}`;
            }
          }

          cart.push({ name: tName, qty: displayQty, tot });
          renderCart();

          document.getElementById('posCode').value = '';
          document.getElementById('posSearch').value = '';
          document.getElementById('posTamilName').value = '';
          document.getElementById('posUnitTag').value = '';
          document.getElementById('posQty').value = '';
          document.getElementById('posRate').value = '';
          document.getElementById('posTotal').value = '';
          currentSelectedProd = null;
        }

        function renderCart() {
          let h = '';
          let sum = 0;
          cart.forEach((it, i) => {
            sum += it.tot;
            h += `<tr>
              <td><b>${it.name}</b></td>
              <td class="text-center">${it.qty}</td>
              <td class="text-right" style="color: #2563eb; font-weight: 700;">₹${it.tot}</td>
              <td class="text-center"><button onclick="cart.splice(${i},1); renderCart();" style="border:none; background:transparent; color:#dc2626; font-weight:800; font-size:16px; cursor:pointer;">❌</button></td>
            </tr>`;
          });
          document.getElementById('cartTable').innerHTML = h;
          document.getElementById('billTotal').innerText = sum.toFixed(2);
        }

        function onCustTypeChange() {
          let ctype = document.getElementById('custType').value;
          let regDiv = document.getElementById('regularCustDiv');
          let regPaidRow = document.getElementById('regularPaidRow');
          let cashNameInput = document.getElementById('cashCustNameInput');
          
          if (ctype === 'ரெகுலர் கஸ்டமர் (Credit)') {
            regDiv.classList.remove('hidden');
            regPaidRow.classList.remove('hidden');
            regPaidRow.style.display = 'flex';
            cashNameInput.classList.add('hidden');
            updatePosCustInfo();
          } else {
            regDiv.classList.add('hidden');
            regPaidRow.classList.add('hidden');
            regPaidRow.style.display = 'none';
            cashNameInput.classList.remove('hidden');
            document.getElementById('billPaidAmt').value = 0;
          }
        }

        async function completeBill(downloadPdf = false) {
          if (cart.length === 0) return alert('பில்லில் பொருள் சேர்க்கவும்!');
          let ctype = document.getElementById('custType').value;
          let cname = '';

          if (ctype === 'ரெகுலர் கஸ்டமர் (Credit)') {
            cname = document.getElementById('regularCustSelect').value;
            if (!cname) return alert('வாடிக்கையாளரைத் தேர்வு செய்யவும்!');
          } else {
            let typedName = document.getElementById('cashCustNameInput').value.trim();
            cname = typedName || 'பொது வாடிக்கையாளர்';
          }

          let total = parseFloat(document.getElementById('billTotal').innerText);
          let paid = (ctype === 'வாடிக்கையாளர் (Cash)') ? total : (parseFloat(document.getElementById('billPaidAmt').value) || 0);

          try {
            let res = await fetch('/api/bill', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ customer_type: ctype, customer_name: cname, items: cart, total, paid })
            });
            let out = await res.json();
            if (out.status === 'ok') {
              generateOutput(out.bill_no, out.time, ctype, cname, cart, total, paid, downloadPdf);
              cart = [];
              document.getElementById('billPaidAmt').value = 0;
              document.getElementById('cashCustNameInput').value = '';
              renderCart();
              await fetchAll();
              
              let curPickerDate = document.getElementById('historyDatePicker').value;
              if (curPickerDate === out.date_key) {
                loadHistoryByDate(curPickerDate);
              }
            } else {
              alert('பில் போடுவதில் பிழை: ' + out.msg);
            }
          } catch(err) {
            alert('சர்வர் தொடர்பு பிழை: ' + err);
          }
        }

        function generateOutput(billNo, timeStr, ctype, cname, items, total, paid, downloadPdf) {
          document.getElementById('rBillNo').innerText = '#' + billNo;
          document.getElementById('rTime').innerText = timeStr;
          
          let custDisplay = cname;
          if (ctype === 'ரெகுலர் கஸ்டமர் (Credit)') {
            custDisplay += ' (Credit Bill)';
          }
          document.getElementById('rCust').innerText = custDisplay;
          
          let rRows = '';
          items.forEach(it => {
            rRows += `<tr>
              <td class="col-item">${it.name}</td>
              <td class="col-qty">${it.qty}</td>
              <td class="col-amt">₹${it.tot}</td>
            </tr>`;
          });
          document.getElementById('rItems').innerHTML = rRows;
          document.getElementById('rTotal').innerText = total;
          
          let paidRow = document.getElementById('rPaidRow');
          if (ctype === 'ரெகுலர் கஸ்டமர் (Credit)' && paid > 0) {
            paidRow.style.display = 'flex';
            document.getElementById('rPaid').innerText = paid;
          } else {
            paidRow.style.display = 'none';
          }

          let receiptElem = document.getElementById('receipt');
          if (downloadPdf) {
            receiptElem.style.display = 'block';
            let opt = {
              margin: 2,
              filename: `Bill_${billNo}_${cname}.pdf`,
              image: { type: 'jpeg', quality: 0.98 },
              html2canvas: { scale: 3 },
              jsPDF: { unit: 'mm', format: [72, 140], orientation: 'portrait' }
            };
            html2pdf().set(opt).from(receiptElem).save().then(() => {
              receiptElem.style.display = 'none';
            });
          } else {
            window.print();
          }
        }

        /* ==================== PRODUCTS TAB ==================== */
        function setNextProductCode() {
          let editBadge = document.getElementById('prodEditBadge');
          if (editBadge && !editBadge.classList.contains('hidden')) return;
          let maxCode = 100;
          db.products.forEach(p => {
            let c = parseInt(p.code);
            if (!isNaN(c) && c > maxCode) maxCode = c;
          });
          document.getElementById('npCode').value = String(maxCode + 1);
        }

        function onTanglishType(val) {
          clearTimeout(transliterateTimer);
          let trimmed = val.trim();
          if (!trimmed) {
            document.getElementById('npPrintName').value = '';
            return;
          }
          
          let l = trimmed.toLowerCase();
          let unitSel = document.getElementById('npUnit');
          let catSel = document.getElementById('npCategory');

          const oilWords = ['gold winner', 'mr gold', 'fortune', 'sunland', 'idayam', 'anandham', 'udhai', 'udhaya', 'ghee', 'ney', 'nei', 'oil', 'ennai', 'enna', 'nallenna', 'kadalenna', 'thengaenna', 'vilakkenna', 'dalda', 'vanaspathi'];
          const soapWords = ['hamam', 'cinthol', 'lifebuoy', 'lux', 'santhoor', 'mysore sandal', 'pears', 'medimix', 'dettol', 'soap', 'colgate', 'close up', 'pepsodent', 'sensodyne', 'paste', 'brush', 'surf', 'aerial', 'tide', 'rin', 'wheel', 'vim', 'exo', 'pril', 'comfort', 'lizol', 'harpic', 'shampoo', 'clinic plus', 'vatika', 'meera', 'chik', 'dhoop', 'agarbathi', 'oothabathi', 'karpooram', 'theepetti', 'thiri'];
          const snackWords = ['marie', 'parle', 'good day', 'bourbon', 'oreo', 'monaco', '50-50', 'milk bikis', 'dark fantasy', 'tiger', 'biscuit', 'biskut', 'rusk', 'cake', 'munch', 'kitkat', 'dairy milk', '5 star', 'chocolate', 'lays', 'kurkure', 'bingo', 'chips', 'mixture', 'sev', 'karasev', 'appalam', 'vadagam', 'maggi', 'yippee', 'noodles'];
          const bevWords = ['3 roses', 'three roses', 'taj mahal', 'avt', 'chakra gold', 'kannan devan', 'red label', 'tea', 'bru', 'sunrise', 'nescafe', 'coffee', 'boost', 'horlicks', 'complan', 'bournvita', 'milo', 'tang', 'rasna', 'bovonto', '7up', 'mirinda', 'coke', 'pepsi', 'maaza'];
          const grainWords = ['ponni', 'baba', 'nandhi', 'delight', 'bullet', 'idly rice', 'pacharisi', 'puzhungal', 'kurunai', 'arisi', 'rice', 'wheat', 'godhumai', 'atta', 'aashirvaad', 'maida', 'ravai', 'sooji', 'semiya', 'vermicelli', 'kambu', 'solam', 'kelvaragu', 'ragi', 'thinai', 'samai'];
          const dalWords = ['thoor', 'thuvaram', 'channa', 'kadalai', 'moong', 'paasi', 'urad', 'ulundu', 'paruppu', 'parupu', 'dal', 'dhal', 'payaru', 'pottukadalai', 'sundal', 'pattani', 'rajma', 'kollu', 'thattai payaru', 'mocha payaru'];
          const sweetWords = ['seeni', 'sakkarai', 'sugar', 'nattu sakkarai', 'vellam', 'mandai vellam', 'karupatti', 'kalkandu', 'uppu', 'salt', 'tata salt', 'kalluppu', 'thooluppu', 'puli', 'valam puli', 'poondu'];
          const spiceWords = ['seeragam', 'jeeragam', 'milagu', 'kadugu', 'sombu', 'venthaiyam', 'pattai', 'krambu', 'elakkai', 'kasakasa', 'biryani ilai', 'sakthi', 'aachi', 'everest', 'mdh', 'masala', 'sambhar thool', 'rasam thool', 'malli thool', 'dhaniya', 'varamillagai', 'vathal', 'manjal thool', 'perungayam'];

          if (oilWords.some(w => l.includes(w))) {
            catSel.value = 'எண்ணெய் & நெய்';
            unitSel.value = 'L';
          } else if (soapWords.some(w => l.includes(w))) {
            catSel.value = 'சோப்பு, பேஸ்ட் & பூஜா';
            unitSel.value = 'Pcs';
          } else if (snackWords.some(w => l.includes(w))) {
            catSel.value = 'சிற்றுண்டி & பிஸ்கட்';
            unitSel.value = 'Pcs';
          } else if (bevWords.some(w => l.includes(w))) {
            catSel.value = 'டீ, காபி & பானங்கள்';
            unitSel.value = 'Pcs';
          } else if (grainWords.some(w => l.includes(w))) {
            catSel.value = 'அரிசி & தானியங்கள்';
            unitSel.value = (l.includes('sippam') || l.includes('mootai') || l.includes('bag')) ? 'Pcs' : 'Kg';
          } else if (dalWords.some(w => l.includes(w))) {
            catSel.value = 'பருப்பு வகைகள்';
            unitSel.value = 'Kg';
          } else if (sweetWords.some(w => l.includes(w))) {
            catSel.value = 'பேக்கிங் & இனிப்பு வகைகள்';
            unitSel.value = 'Kg';
          } else if (spiceWords.some(w => l.includes(w))) {
            catSel.value = 'மசாலா & வாசனைப் பொருட்கள்';
            unitSel.value = 'Kg';
          }

          transliterateTimer = setTimeout(async () => {
            try {
              let url = `https://inputtools.google.com/request?text=${encodeURIComponent(trimmed)}&itc=ta-t-i0-und&num=1`;
              let res = await fetch(url);
              let data = await res.json();
              if (data && data[0] === 'SUCCESS' && data[1][0][1].length > 0) {
                let tamilText = data[1][0][1][0];
                document.getElementById('npPrintName').value = tamilText;

                if (tamilText.includes('எண்ணெய்') || tamilText.includes('நெய்')) {
                  catSel.value = 'எண்ணெய் & நெய்';
                  unitSel.value = 'L';
                } else if (tamilText.includes('பருப்பு') || tamilText.includes('உளுந்து')) {
                  catSel.value = 'பருப்பு வகைகள்';
                  unitSel.value = 'Kg';
                } else if (tamilText.includes('அரிசி') || tamilText.includes('ரவை') || tamilText.includes('கோதுமை')) {
                  catSel.value = 'அரிசி & தானியங்கள்';
                } else if (tamilText.includes('சீனி') || tamilText.includes('சர்க்கரை') || tamilText.includes('வெல்லம்') || tamilText.includes('உப்பு')) {
                  catSel.value = 'பேக்கிங் & இனிப்பு வகைகள்';
                } else if (tamilText.includes('சீரகம்') || tamilText.includes('மிளகு') || tamilText.includes('மஞ்சள்') || tamilText.includes('மசாலா')) {
                  catSel.value = 'மசாலா & வாசனைப் பொருட்கள்';
                } else if (tamilText.includes('சோப்பு') || tamilText.includes('பேஸ்ட்')) {
                  catSel.value = 'சோப்பு, பேஸ்ட் & பூஜா';
                  unitSel.value = 'Pcs';
                }
              }
            } catch(err) {
              document.getElementById('npPrintName').value = trimmed;
            }
          }, 250);
        }

        function resetAndFilterProducts() {
          let q = (document.getElementById('prodSearchInput').value || '').trim().toLowerCase();
          let selectedCat = document.getElementById('catFilterSelect').value;

          filteredProductsList = db.products.filter(p => {
            let matchesCat = (selectedCat === 'ALL') || (p.category === selectedCat);
            let pCode = String(p.code);
            let pName = (p.name || '').toLowerCase();
            let pPrint = (p.print_name || '').toLowerCase();
            let matchesSearch = !q || pCode.includes(q) || pName.includes(q) || pPrint.includes(q);
            return matchesCat && matchesSearch;
          });

          prodDisplayLimit = 20;
          renderProductListChunks();
        }

        function renderProductListChunks() {
          let listDiv = document.getElementById('prodList');
          if (filteredProductsList.length === 0) {
            listDiv.innerHTML = '<p style="text-align:center; font-size:12px; color:#64748b; padding:15px;">பொருட்கள் எதுவும் இல்லை.</p>';
            return;
          }

          let itemsToRender = filteredProductsList.slice(0, prodDisplayLimit);
          let h = '';
          itemsToRender.forEach(p => {
            let catBadge = p.category ? `<span style="font-size:10px; background:#eff6ff; color:#1d4ed8; padding:1px 6px; border-radius:4px; border:1px solid #bfdbfe; margin-left:4px;">${p.category}</span>` : '';
            h += `<div style="display:flex; justify-content:space-between; align-items:center; background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #cbd5e1; font-size:13px; font-weight:700;">
                    <div style="flex:1;">
                      <span>🏷️ [${p.code}] ${p.print_name} ${catBadge}</span>
                      <div style="font-size:11px; color:#64748b; font-weight:500;">${p.name} | ₹${p.price} / ${p.unit}</div>
                    </div>
                    <div style="display:flex; gap:4px;">
                      <button onclick="populateProdEdit('${p.code}', '${p.name}', '${p.print_name}', '${p.unit}', ${p.price}, '${p.category || 'பொதுவானவை'}')" class="btn btn-soft-blue" style="padding:4px 8px; font-size:11px; min-height:30px;">Edit</button>
                      <button onclick="deleteProduct('${p.code}')" class="btn btn-red" style="padding:4px 8px; font-size:11px; min-height:30px;">நீக்கு</button>
                    </div>
                  </div>`;
          });

          if (prodDisplayLimit < filteredProductsList.length) {
            h += `<div style="text-align:center; padding:8px; font-size:11px; color:#64748b; font-weight:700;">மேலும் பார்க்க கீழே ஸ்க்ரோல் செய்யவும்... (${itemsToRender.length}/${filteredProductsList.length})</div>`;
          }

          listDiv.innerHTML = h;
        }

        function onProdListScroll(el) {
          if (el.scrollTop + el.clientHeight >= el.scrollHeight - 30) {
            if (prodDisplayLimit < filteredProductsList.length) {
              prodDisplayLimit += 20;
              renderProductListChunks();
            }
          }
        }

        async function saveProduct() {
          let code = document.getElementById('npCode').value.trim();
          let name = document.getElementById('npName').value.trim();
          let print_name = document.getElementById('npPrintName').value.trim() || name;
          let unit = document.getElementById('npUnit').value;
          let price = parseFloat(document.getElementById('npRate').value);
          let category = document.getElementById('npCategory').value;

          if (!code || !name || isNaN(price)) return alert('அனைத்து விவரங்களையும் உள்ளிடவும்!');

          let newObj = { code, name, print_name, unit, price, category };

          try {
            let res = await fetch('/api/product', { 
              method: 'POST', 
              headers: {'Content-Type': 'application/json'}, 
              body: JSON.stringify(newObj) 
            });
            let out = await res.json();
            if (out.status === 'exists') {
              alert(out.msg);
              return;
            }
            if (out.status === 'ok') {
              clearProdForm();
              await fetchAll();
              alert('பொருள் வெற்றிகரமாகச் சேமிக்கப்பட்டது!');
            } else {
              alert('பொருள் சேமிப்பதில் பிழை: ' + out.msg);
            }
          } catch(e) {
            alert('சர்வர் தொடர்பு பிழை: ' + e);
          }
        }

        function clearProdForm() {
          document.getElementById('npName').value = '';
          document.getElementById('npPrintName').value = '';
          document.getElementById('npRate').value = '';
          document.getElementById('prodFormTitle').innerText = '➕ புதிய பொருள் சேர்த்தல்';
          document.getElementById('btnSaveProd').innerText = '💾 சேமி';
          document.getElementById('prodEditBadge').classList.add('hidden');
          setNextProductCode();
        }

        function populateProdEdit(code, name, print_name, unit, price, category) {
          document.getElementById('npCode').value = code;
          document.getElementById('npName').value = name;
          document.getElementById('npPrintName').value = print_name;
          document.getElementById('npUnit').value = unit;
          document.getElementById('npRate').value = price;
          document.getElementById('npCategory').value = category || 'பொதுவானவை';
          document.getElementById('prodFormTitle').innerText = '✏️ விலை திருத்தம் (' + code + ')';
          document.getElementById('btnSaveProd').innerText = '💾 Update';
          document.getElementById('prodEditBadge').classList.remove('hidden');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        async function deleteProduct(code) {
          if (!confirm(`பொருள் கோட் [${code}]-ஐ நீக்கவா?`)) return;
          try {
            let res = await fetch(`/api/product/${code}`, { method: 'DELETE' });
            let out = await res.json();
            if (out.status === 'ok') {
              await fetchAll();
              alert('பொருள் நீக்கப்பட்டது!');
            } else {
              alert('நீக்குவதில் பிழை: ' + out.msg);
            }
          } catch(e) {
            alert('நீக்குவதில் பிழை: ' + e);
          }
        }

        /* ==================== CUSTOMER & PASSBOOK ==================== */
        function onCustomerTanglishType(val) {
          clearTimeout(custTransliterateTimer);
          let trimmed = val.trim();
          if (!trimmed) {
            document.getElementById('ncName').value = '';
            return;
          }
          document.getElementById('ncName').value = trimmed;

          custTransliterateTimer = setTimeout(async () => {
            try {
              let url = `https://inputtools.google.com/request?text=${encodeURIComponent(trimmed)}&itc=ta-t-i0-und&num=1`;
              let res = await fetch(url);
              let data = await res.json();
              if (data && data[0] === 'SUCCESS' && data[1][0][1].length > 0) {
                document.getElementById('ncName').value = data[1][0][1][0];
              }
            } catch(err) {}
          }, 200);
        }

        function renderCustomerDropdowns() {
          let sel = document.getElementById('regularCustSelect');
          let paySel = document.getElementById('payCustSelect');
          sel.innerHTML = '';
          paySel.innerHTML = '';
          db.customers.forEach(c => {
            sel.innerHTML += `<option value="${c.name}" data-bal="${c.balance}">${c.name}</option>`;
            paySel.innerHTML += `<option value="${c.id}">${c.name} (Credit: ₹${parseFloat(c.balance).toFixed(2)})</option>`;
          });
          updatePosCustInfo();
        }

        function updatePosCustInfo() {
          let sel = document.getElementById('regularCustSelect');
          if(sel && sel.selectedIndex >= 0 && sel.value !== '') {
            let bal = parseFloat(sel.options[sel.selectedIndex].dataset.bal || 0);
            document.getElementById('posCustBalBadge').innerText = '📌 கணக்கு இருப்பு: ₹' + bal.toFixed(2);
          } else {
            document.getElementById('posCustBalBadge').innerText = '';
          }
        }

        async function saveCustomer() {
          let name = document.getElementById('ncName').value.trim();
          let balance = parseFloat(document.getElementById('ncBal').value) || 0;
          
          if (!name) return alert('வாடிக்கையாளர் பெயரை உள்ளிடவும்!');

          try {
            let res = await fetch('/api/customer', { 
              method: 'POST', 
              headers: {'Content-Type': 'application/json'}, 
              body: JSON.stringify({id: 0, name, balance}) 
            });
            let out = await res.json();
            if (out.status === 'exists') {
              alert(out.msg);
            } else if (out.status === 'ok') {
              document.getElementById('ncTanglishName').value = '';
              document.getElementById('ncName').value = '';
              document.getElementById('ncBal').value = '0';
              await fetchAll();
              alert('வாடிக்கையாளர் கணக்கு சேமிக்கப்பட்டது!');
            } else {
              alert('சேமிப்பில் பிழை: ' + out.msg);
            }
          } catch(err) {
            alert('சர்வர் பிழை: ' + err);
          }
        }

        async function deleteCustomer(cid, name) {
          if (!confirm(`'${name}' வாடிக்கையாளரையும் அவரது கணக்குகளையும் நீக்கவா?`)) return;
          try {
            let res = await fetch(`/api/customer/${cid}`, { method: 'DELETE' });
            let out = await res.json();
            if (out.status === 'ok') {
              await fetchAll();
              alert('வாடிக்கையாளர் நீக்கப்பட்டார்!');
            } else {
              alert('நீக்குவதில் பிழை: ' + out.msg);
            }
          } catch(err) {
            alert('சர்வர் பிழை: ' + err);
          }
        }

        async function submitDirectPayment() {
          let sel = document.getElementById('payCustSelect');
          if (!sel.value) return alert('வாடிக்கையாளரைத் தேர்வு செய்யவும்!');
          let cid = parseInt(sel.value);
          let amount = parseFloat(document.getElementById('payAmount').value);
          if (!cid || isNaN(amount) || amount <= 0) return alert('சரியான வரவுத் தொகையை உள்ளிடவும்!');
          
          try {
            let res = await fetch('/api/customer/payment', { 
              method: 'POST', 
              headers: {'Content-Type': 'application/json'}, 
              body: JSON.stringify({customer_id: cid, amount}) 
            });
            let out = await res.json();
            if (out.status === 'ok') {
              document.getElementById('payAmount').value = '';
              await fetchAll();
              alert('வரவு வைக்கப்பட்டது!');
            } else {
              alert('வரவு வைப்பதில் பிழை: ' + out.msg);
            }
          } catch(err) {
            alert('சர்வர் பிழை: ' + err);
          }
        }

        function renderLedgerList() {
          let h = '';
          if (db.customers.length === 0) {
            h = '<p style="text-align:center; font-size:12px; color:#64748b; padding:15px;">வாடிக்கையாளர்கள் இல்லை.</p>';
          } else {
            db.customers.forEach(c => {
              h += `<div style="display:flex; justify-content:space-between; align-items:center; background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #cbd5e1; font-size:13px; font-weight:700; margin-bottom:5px;">
                      <div onclick="openPassbook(${c.id}, '${c.name}', ${c.balance})" style="flex:1; cursor:pointer;">
                        <span style="font-size:13.5px; color:#1e3a8a;">🏨 ${c.name}</span>
                        <div style="color:#1e40af; font-size:11.5px; margin-top:1px;">கணக்கு இருப்பு: ₹${parseFloat(c.balance).toFixed(2)} ➡️</div>
                      </div>
                      <div>
                        <button onclick="deleteCustomer(${c.id}, '${c.name}')" title="நீக்கு" style="border:none; background:#fee2e2; color:#dc2626; font-size:14px; font-weight:900; padding:6px 10px; border-radius:6px; cursor:pointer;">❌</button>
                      </div>
                    </div>`;
            });
          }
          document.getElementById('ledgerList').innerHTML = h;
        }

        function openPassbook(cid, name, bal) {
          activePbCustomer = { cid, name, bal };
          document.getElementById('pbCustName').innerText = '🏨 ' + name;
          document.getElementById('pbCustBal').innerText = 'தற்போதைய இருப்பு: ₹' + parseFloat(bal).toFixed(2);
          document.getElementById('pbPrintCustName').innerText = 'வாடிக்கையாளர்: ' + name;
          document.getElementById('pbPrintCustBal').innerText = 'இருப்பு: ₹' + parseFloat(bal).toFixed(2);

          fetch(`/api/customer/ledger/${cid}`).then(r => r.json()).then(out => {
            let rows = '';
            let ledgerData = out.ledger || [];
            if (ledgerData.length === 0) {
              rows = '<tr><td colspan="5" class="text-center" style="padding:12px; color:#000;">பரிவர்த்தனை ஏதும் இல்லை</td></tr>';
            } else {
              ledgerData.forEach(l => {
                rows += `<tr>
                  <td style="color:#000; font-size:10px;">${l.txn_date}</td>
                  <td style="color:#000; font-size:11px;"><b>${l.description}</b></td>
                  <td class="text-right" style="color:#000;">${l.debit > 0 ? '₹'+parseFloat(l.debit).toFixed(2) : '-'}</td>
                  <td class="text-right" style="color:#000;">${l.credit > 0 ? '₹'+parseFloat(l.credit).toFixed(2) : '-'}</td>
                  <td class="text-right" style="color:#000;"><b>₹${parseFloat(l.balance).toFixed(2)}</b></td>
                </tr>`;
              });
            }
            document.getElementById('pbTableBody').innerHTML = rows;
            document.getElementById('passbookModal').classList.remove('hidden');
          });
        }

        function closePassbook() {
          document.getElementById('passbookModal').classList.add('hidden');
        }

        function downloadPassbookPdf() {
          let element = document.getElementById('passbookPrintArea');
          let opt = {
            margin: 6,
            filename: `Passbook_${activePbCustomer.name}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2 },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
          };
          html2pdf().set(opt).from(element).save();
        }

        /* ==================== ZERO-LAG HISTORY & TAP-TO-PREVIEW ==================== */
        async function loadHistoryByDate(dateStr) {
          if (!dateStr) return;
          let listDiv = document.getElementById('billHistoryList');
          listDiv.innerHTML = '<p style="text-align:center; font-size:12px; color:#64748b; padding:10px;">ஏற்றுகிறது...</p>';
          
          try {
            let res = await fetch(`/api/bills/by-date/${dateStr}`);
            let data = await res.json();
            currentDayBills = data.bills || [];
            
            document.getElementById('histCountLabel').innerText = 'பில்கள்: ' + currentDayBills.length;
            document.getElementById('historySearchInput').value = '';

            renderBillsList(currentDayBills);
          } catch(err) {
            listDiv.innerHTML = '<p style="text-align:center; color:#dc2626;">டேட்டா பெறுவதில் சிக்கல்.</p>';
          }
        }

        function filterHistoryList(query) {
          let q = query.trim().toLowerCase();
          if (!q) {
            renderBillsList(currentDayBills);
            return;
          }
          let filtered = currentDayBills.filter(b => 
            String(b.bill_no).includes(q) || 
            b.customer_name.toLowerCase().includes(q) ||
            b.customer_type.toLowerCase().includes(q)
          );
          renderBillsList(filtered);
        }

        function renderBillsList(bills) {
          let listDiv = document.getElementById('billHistoryList');
          if (bills.length === 0) {
            listDiv.innerHTML = '<p style="text-align:center; font-size:12px; color:#64748b; padding:15px;">பில்கள் எதுவும் இல்லை.</p>';
            return;
          }

          let h = '';
          bills.forEach((b, idx) => {
            let badge = b.customer_type.includes('Credit') ? '<span style="font-size:10px; background:#eff6ff; color:#1e40af; padding:1px 5px; border-radius:4px; border:1px solid #bfdbfe; margin-left:4px;">Credit</span>' : '';
            h += `<div style="background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #cbd5e1; font-size:12px; margin-bottom:5px; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                    <div onclick="openBillPreview(${idx})" style="display:flex; justify-content:space-between; font-weight:800; font-size:13px; cursor:pointer;">
                      <span>#${b.bill_no} - 🏨 ${b.customer_name} ${badge}</span>
                      <span style="color:#2563eb;">₹${parseFloat(b.total).toFixed(2)} 🔍</span>
                    </div>
                    <div onclick="openBillPreview(${idx})" style="font-size:10.5px; color:#64748b; margin-top:2px; cursor:pointer;">${b.time_str}</div>
                    <div style="display:flex; gap:5px; margin-top:6px;">
                      <button onclick='generateOutput(${b.bill_no}, "${b.time_str}", "${b.customer_type}", "${b.customer_name}", ${JSON.stringify(b.items)}, ${b.total}, ${b.paid || 0}, false)' class="btn btn-blue" style="flex:1.2; padding:4px; font-size:11px; min-height:32px;">🖨️ Re-Print</button>
                      <button onclick='generateOutput(${b.bill_no}, "${b.time_str}", "${b.customer_type}", "${b.customer_name}", ${JSON.stringify(b.items)}, ${b.total}, ${b.paid || 0}, true)' class="btn btn-soft-amber" style="flex:0.8; padding:4px; font-size:11px; min-height:32px;">📥 PDF</button>
                    </div>
                  </div>`;
          });
          listDiv.innerHTML = h;
        }

        function openBillPreview(idx) {
          let b = currentDayBills[idx];
          if (!b) return;

          document.getElementById('prevBillTitle').innerText = `பில் #${b.bill_no} - ${b.customer_name}`;
          document.getElementById('prevBillTime').innerText = `${b.time_str} (${b.customer_type})`;
          document.getElementById('prevBillTotalVal').innerText = `₹${parseFloat(b.total).toFixed(2)}`;

          let rows = '';
          (b.items || []).forEach(it => {
            rows += `<tr>
              <td><b>${it.name}</b></td>
              <td class="text-center">${it.qty}</td>
              <td class="text-right" style="color: #2563eb; font-weight: 700;">₹${it.tot}</td>
            </tr>`;
          });
          document.getElementById('prevBillItemsBody').innerHTML = rows;

          document.getElementById('prevBtnPrint').onclick = function() {
            generateOutput(b.bill_no, b.time_str, b.customer_type, b.customer_name, b.items, b.total, b.paid || 0, false);
          };
          document.getElementById('prevBtnPdf').onclick = function() {
            generateOutput(b.bill_no, b.time_str, b.customer_type, b.customer_name, b.items, b.total, b.paid || 0, true);
          };

          document.getElementById('billPreviewModal').classList.remove('hidden');
        }

        function closeBillPreview() {
          document.getElementById('billPreviewModal').classList.add('hidden');
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
            setNextProductCode();
            resetAndFilterProducts();
          } else if(t === 'ledger') {
            document.getElementById('viewLedger').classList.remove('hidden');
            document.getElementById('tabLedger').className = "tab-btn active";
          } else {
            document.getElementById('viewHistory').classList.remove('hidden');
            document.getElementById('tabHistory').className = "tab-btn active";
            let pickerVal = document.getElementById('historyDatePicker').value || getTodayDateStr();
            loadHistoryByDate(pickerVal);
          }
        }
      </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)