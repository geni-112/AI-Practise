import duckdb
import random
from faker import Faker
from datetime import date, timedelta
import os

fake = Faker('zh_CN')
random.seed(42)
Faker.seed(42)

DB_PATH = os.path.join(os.path.dirname(__file__), 'retail.duckdb')

REGIONS = [
    ('R001', '华东', '上海'), ('R002', '华东', '江苏'), ('R003', '华东', '浙江'),
    ('R004', '华东', '安徽'), ('R005', '华南', '广东'), ('R006', '华南', '广西'),
    ('R007', '华南', '海南'), ('R008', '华南', '福建'), ('R009', '华北', '北京'),
    ('R010', '华北', '天津'), ('R011', '华北', '河北'), ('R012', '华北', '山东'),
    ('R013', '西部', '四川'), ('R014', '西部', '重庆'), ('R015', '西部', '陕西'),
    ('R016', '西部', '云南'), ('R017', '华中', '湖北'), ('R018', '华中', '湖南'),
    ('R019', '华中', '河南'), ('R020', '东北', '辽宁'),
]

CATEGORIES = ['电子', '服装', '食品', '家居', '运动']

PRODUCTS = []
for i in range(1, 201):
    cat = random.choice(CATEGORIES)
    name_map = {
        '电子': ['智能手机', '笔记本电脑', '平板电脑', '蓝牙耳机', '智能手表', '充电宝', '显示器', '键盘'],
        '服装': ['T恤', '牛仔裤', '连衣裙', '运动夹克', '羽绒服', '衬衫', '短裤', '毛衣'],
        '食品': ['坚果礼盒', '有机茶叶', '进口咖啡', '零食大礼包', '蜂蜜', '橄榄油', '饼干', '巧克力'],
        '家居': ['床上用品', '收纳箱', '香薰蜡烛', '桌面摆件', '厨房刀具', '保温杯', '台灯', '地毯'],
        '运动': ['跑步鞋', '瑜伽垫', '哑铃套装', '运动水壶', '健身手套', '跳绳', '护膝', '背包'],
    }
    base_name = random.choice(name_map[cat])
    price_map = {'电子': (299, 8999), '服装': (49, 999), '食品': (19, 299), '家居': (29, 599), '运动': (39, 799)}
    lo, hi = price_map[cat]
    price = round(random.uniform(lo, hi), 2)
    supplier = fake.company()
    PRODUCTS.append((f'P{i:03d}', f'{base_name}-{i:03d}', cat, price, supplier))

CUSTOMERS = []
provinces = [r[2] for r in REGIONS]
for i in range(1, 1001):
    prov = random.choice(provinces)
    city = fake.city()
    tier = random.choices(['A', 'B', 'C'], weights=[0.2, 0.5, 0.3])[0]
    CUSTOMERS.append((f'C{i:04d}', fake.company(), city, prov, tier))

def random_date(start, end):
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))

START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 12, 31)

print(f"Generating data into {DB_PATH}...")

con = duckdb.connect(DB_PATH)

con.execute("DROP TABLE IF EXISTS orders")
con.execute("DROP TABLE IF EXISTS products")
con.execute("DROP TABLE IF EXISTS customers")
con.execute("DROP TABLE IF EXISTS regions")

con.execute("""
CREATE TABLE regions (
    region_id VARCHAR PRIMARY KEY,
    region_name VARCHAR,
    province VARCHAR
)
""")
con.executemany("INSERT INTO regions VALUES (?, ?, ?)", REGIONS)
print(f"  regions: {len(REGIONS)} rows")

con.execute("""
CREATE TABLE customers (
    customer_id VARCHAR PRIMARY KEY,
    customer_name VARCHAR,
    city VARCHAR,
    province VARCHAR,
    tier VARCHAR
)
""")
con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", CUSTOMERS)
print(f"  customers: {len(CUSTOMERS)} rows")

con.execute("""
CREATE TABLE products (
    product_id VARCHAR PRIMARY KEY,
    product_name VARCHAR,
    category VARCHAR,
    unit_price DECIMAL(10,2),
    supplier VARCHAR
)
""")
con.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", PRODUCTS)
print(f"  products: {len(PRODUCTS)} rows")

con.execute("""
CREATE TABLE orders (
    order_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR,
    product_id VARCHAR,
    quantity INTEGER,
    unit_price DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    order_date DATE,
    region_name VARCHAR,
    province VARCHAR,
    status VARCHAR
)
""")

BATCH_SIZE = 5000
TOTAL_ORDERS = 100000
orders_batch = []
statuses = ['completed', 'completed', 'completed', 'completed', 'returned', 'pending']

for i in range(1, TOTAL_ORDERS + 1):
    cust = random.choice(CUSTOMERS)
    prod = random.choice(PRODUCTS)
    qty = random.randint(1, 10)
    price = prod[3]
    total = round(qty * price, 2)
    odate = random_date(START_DATE, END_DATE)
    prov = cust[3]
    region_row = next(r for r in REGIONS if r[2] == prov)
    region = region_row[1]
    status = random.choice(statuses)
    orders_batch.append((
        f'O{i:07d}', cust[0], prod[0], qty, price, total,
        odate, region, prov, status
    ))
    if len(orders_batch) == BATCH_SIZE:
        con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", orders_batch)
        orders_batch = []
        print(f"  orders: {i}/{TOTAL_ORDERS}", end='\r')

if orders_batch:
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", orders_batch)

count = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
print(f"\n  orders: {count} rows")

con.close()
print("Done! Demo data generated successfully!")
