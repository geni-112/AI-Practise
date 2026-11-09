"""Reproducible, fictional English commerce data. Exactly 10,000 source rows."""
from __future__ import annotations
import csv, json, random, sqlite3, hashlib
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
R = random.Random(20261106)
DATA = ROOT / 'data'
PUBLIC = ROOT / 'public'
REGIONS = ['Mexico City', 'North', 'Central', 'Pacific', 'South']
CITIES = {'Mexico City':['Mexico City'], 'North':['Monterrey','Tijuana'], 'Central':['Puebla','Queretaro'], 'Pacific':['Guadalajara','Mazatlan'], 'South':['Merida','Oaxaca']}
CATEGORIES = ['Electronics','Home & Living','Fashion','Sports','Beauty','Books']
CHANNELS = ['Online Store','Marketplace','Mobile App','Retail']
FIRST = ['Alex','Jordan','Taylor','Morgan','Sam','Casey','Riley','Jamie','Avery','Drew','Quinn','Robin','Cameron','Reese','Blake']
LAST = ['Rivera','Garcia','Lopez','Martinez','Smith','Cruz','Reed','Brooks','Diaz','Flores','Chen','Patel']
PRODUCTS = {
 'Electronics':['Wireless Headphones','USB-C Dock','Smart Speaker','Portable Charger','Mechanical Keyboard'],
 'Home & Living':['Linen Cushion','Desk Lamp','Coffee Grinder','Storage Basket','Ceramic Mug'],
 'Fashion':['Cotton T-Shirt','Canvas Tote','Running Cap','Denim Jacket','Everyday Sneakers'],
 'Sports':['Yoga Mat','Resistance Bands','Water Bottle','Training Shorts','Fitness Tracker'],
 'Beauty':['Daily Moisturizer','Sunscreen SPF50','Gentle Cleanser','Hand Cream','Vitamin C Serum'],
 'Books':['Design Handbook','Cooking Essentials','Science Atlas','Travel Journal','Modern Fiction']}

def generate():
    R.seed(20261106)
    tables = {}
    tables['tenants'] = [{'tenant_id':'luma','tenant_name':'Luma Commerce','country':'Mexico'}, {'tenant_id':'northstar','tenant_name':'Northstar Retail','country':'Mexico'}]
    customers=[]
    for i in range(900):
        tenant='luma' if i<450 else 'northstar'; reg=R.choice(REGIONS)
        customers.append({'customer_id':f'CUS-{i+1:04}', 'tenant_id':tenant,'customer_name':f'{R.choice(FIRST)} {R.choice(LAST)}', 'email':f'customer{i+1:04}@example.test','phone':None if i%50==0 else f'+52-555-{i+1000:04}', 'region':reg,'city':R.choice(CITIES[reg]),'segment':R.choice(['Consumer','Small Business','Enterprise']),'created_at':str(date(2025,1,1)+timedelta(days=R.randrange(600)))})
    tables['customers']=customers
    products=[]
    for i in range(120):
        cat=CATEGORIES[(i%60)//10]; base=R.uniform(10,200)
        products.append({'product_id':f'SKU-{i+1:04}','tenant_id':'luma' if i<60 else 'northstar','product_name':PRODUCTS[cat][i%5] + (' Pro' if i%10>=5 else ' Essential'),'category':cat,'brand':R.choice(['Luma Studio','Northline','Everday','Forma','Alta']),'unit_price':round(base,2),'unit_cost':round(base*R.uniform(.35,.7),2),'currency':'USD'})
    tables['products']=products
    campaigns=[]
    for i in range(24):
        campaigns.append({'campaign_id':f'CMP-{i+1:03}','tenant_id':'luma' if i<12 else 'northstar','campaign_name':f'{R.choice(["Autumn Essentials","Weekend Discovery","October Favorites","New Season"])} {i+1:02}','platform':R.choice(['Google Ads','Meta Ads','TikTok Ads']),'channel':R.choice(['Paid Search','Paid Social','Display']),'start_date':'2026-10-01','budget_usd':R.randrange(20,80)*100})
    orders=[];items=[]
    for i in range(2600):
        tenant='luma' if i<1300 else 'northstar'; cs=R.choice(customers[:450] if tenant=='luma' else customers[450:])
        # Trend and regional effects are deterministic features for meaningful BI.
        day=date(2026,4,1)+timedelta(days=R.randrange(214)); status=R.choices(['Completed','Processing','Cancelled'],[.88,.08,.04])[0]
        orders.append({'order_id':f'ORD-{i+1:05}','tenant_id':tenant,'customer_id':cs['customer_id'],'order_date':str(day),'region':cs['region'],'channel':R.choice(CHANNELS),'status':status,'campaign_id':R.choice(campaigns[:12] if tenant=='luma' else campaigns[12:])['campaign_id'],'currency':'USD','gross_amount':0.,'discount_amount':0.,'net_amount':0.})
    for i in range(3500):
        order=orders[i] if i<2600 else R.choice(orders); tenant=order['tenant_id']
        product=R.choice(products[:60] if tenant=='luma' else products[60:]); qty=R.choices([1,2,3,4],[.65,.23,.09,.03])[0]
        gross=round(product['unit_price']*qty,2); discount=round(gross*R.choice([0,0,.05,.10,.15]),2)
        line={'item_id':f'ITEM-{i+1:05}','tenant_id':tenant,'order_id':order['order_id'],'product_id':product['product_id'],'quantity':qty,'unit_price':product['unit_price'],'discount_amount':discount,'net_amount':round(gross-discount,2)}
        items.append(line)
        for field,val in [('gross_amount',gross),('discount_amount',discount),('net_amount',line['net_amount'])]:order[field]=round(order[field]+val,2)
    tables['orders']=orders;tables['order_items']=items
    inventories=[]
    for i in range(240):
        p=products[i%120]
        inventories.append({'inventory_id':f'INV-{i+1:04}','tenant_id':p['tenant_id'],'product_id':p['product_id'],'warehouse': 'Mexico City DC' if i<120 else 'Monterrey DC','stock_on_hand':-2 if i%47==0 else R.randrange(0,180),'reorder_point':20,'snapshot_date':'2026-10-31'})
    tables['inventory']=inventories
    completed=[o for o in orders if o['status']=='Completed']
    returns=[]
    for i,o in enumerate(R.sample(completed,250)):
        returns.append({'return_id':f'RET-{i+1:04}','tenant_id':o['tenant_id'],'order_id':o['order_id'],'return_date':str(date.fromisoformat(o['order_date'])+timedelta(days=R.randrange(1,6))),'reason':R.choice(['Wrong Size','Damaged Item','Changed Mind','Not as Described','Late Delivery']),'refund_amount':round(o['net_amount']*R.choice([.25,.5,1]),2),'status':R.choice(['Approved','Approved','Pending'])})
    tables['returns']=returns
    shipments=[]
    for i,o in enumerate(R.sample(completed,900)):
        promised=R.randrange(2,6);actual=promised+R.choice([-1,0,0,0,1,2,4])
        shipments.append({'shipment_id':f'SHP-{i+1:04}','tenant_id':o['tenant_id'],'order_id':o['order_id'],'carrier':R.choice(['ParcelOne','SwiftRoute','MetroShip']),'promised_days':promised,'actual_days':actual,'shipping_cost':round(R.uniform(2,15),2),'status':'Delivered'})
    tables['shipments']=shipments;tables['campaigns']=campaigns
    ads=[]
    for i in range(600):
        c=campaigns[i%24];impressions=R.randrange(2000,22000);clicks=round(impressions*R.uniform(.01,.065));conversions=round(clicks*R.uniform(.02,.12));spend=round(clicks*R.uniform(.18,.85),2)
        ads.append({'metric_id':f'AD-{i+1:04}','tenant_id':c['tenant_id'],'campaign_id':c['campaign_id'],'metric_date':str(date(2026,10,1)+timedelta(days=i//24)),'impressions':impressions,'clicks':clicks,'conversions':conversions,'spend_usd':spend,'attributed_revenue_usd':round(conversions*R.uniform(35,130),2),'source':'Synthetic advertising API'})
    tables['ad_metrics']=ads
    competitors=[]
    for i in range(480):
        p=products[i%120]
        competitors.append({'price_id':f'PRICE-{i+1:04}','tenant_id':p['tenant_id'],'product_id':p['product_id'],'competitor':R.choice(['ShopVista','DealHarbor','MarketNest']),'observed_date':f'2026-10-{[7,14,21,28][i//120]:02}','price_usd':round(p['unit_price']*R.uniform(.8,1.2),2),'in_stock':R.choice([True,True,True,False]),'source':'Synthetic competitor feed'})
    tables['competitor_prices']=competitors
    reviews=[]
    for i in range(384):
        p=R.choice(products);rating=R.choices([1,2,3,4,5],[.05,.08,.12,.30,.45])[0]
        reviews.append({'review_id':f'REV-{i+1:04}','tenant_id':p['tenant_id'],'product_id':p['product_id'],'review_date':str(date(2026,9,1)+timedelta(days=R.randrange(61))),'rating':rating,'review_text':R.choice(['Excellent quality and fast delivery.','Great value and easy to use.','Exactly what I needed for everyday use.']) if rating>=4 else R.choice(['Delivery arrived later than expected.','The product quality could be improved.','Packaging was damaged on arrival.']),'sentiment':'Positive' if rating>=4 else 'Neutral' if rating==3 else 'Negative','source':'Synthetic marketplace reviews','language':'English'})
    tables['reviews']=reviews
    assert sum(map(len,tables.values()))==10000
    DATA.mkdir(exist_ok=True);PUBLIC.mkdir(exist_ok=True)
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    db=sqlite3.connect(runtime/'warehouse.db');db.execute('PRAGMA foreign_keys=ON')
    schema=[]
    for name,rows in tables.items():
        cols=list(rows[0]);types={c:('INTEGER' if isinstance(next((r[c] for r in rows if r[c] is not None),''),(int,bool)) else 'REAL' if isinstance(next((r[c] for r in rows if r[c] is not None),''),float) else 'TEXT') for c in cols}
        db.execute(f'DROP TABLE IF EXISTS "{name}"')
        ddl=f'CREATE TABLE "{name}" ('+', '.join(f'"{c}" {types[c]}' for c in cols)+')'
        db.execute(ddl);db.executemany(f'INSERT INTO "{name}" VALUES ('+','.join('?' for _ in cols)+')',[[r[c] for c in cols] for r in rows]);schema.append(ddl+';')
        with (DATA/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
    db.commit();db.close()
    manifest={'synthetic':True,'seed':20261106,'language':'English','currency':'USD','row_count':10000,'tables':{k:len(v) for k,v in tables.items()},'quality_scenarios':{'missing_customer_phones':sum(r['phone'] is None for r in customers),'negative_inventory':sum(r['stock_on_hand']<0 for r in inventories)},'notice':'All records, names, competitors, reviews and advertising feeds are fictional. No real external data is collected.'}
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (DATA/'schema.sql').write_text('\n'.join(schema)+'\n')
    (PUBLIC/'demo-data.json').write_text(json.dumps({'manifest':manifest,'tables':tables},separators=(',',':')))
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':generate()
