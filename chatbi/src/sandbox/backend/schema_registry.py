from dotenv import load_dotenv
load_dotenv()

SCHEMA_DESCRIPTION = """
数据库：零售业务演示数据库（DuckDB）
数据范围：2023年1月1日 至 2025年12月31日

表1：orders（订单表，约10万行）
- order_id: VARCHAR, 订单唯一ID
- customer_id: VARCHAR, 客户ID，关联 customers.customer_id
- product_id: VARCHAR, 产品ID，关联 products.product_id
- quantity: INTEGER, 购买数量
- unit_price: DECIMAL(10,2), 成交单价（元）
- total_amount: DECIMAL(10,2), 订单总金额 = quantity × unit_price（元）
- order_date: DATE, 下单日期（YYYY-MM-DD格式）
- region_name: VARCHAR, 销售大区（华东/华南/华北/西部/华中/东北）
- province: VARCHAR, 省份
- status: VARCHAR, 订单状态（completed=已完成, returned=已退货, pending=待处理）
注意：统计销售额时，默认只计算 status='completed' 的订单

表2：products（产品表，200行）
- product_id: VARCHAR, 产品唯一ID
- product_name: VARCHAR, 产品名称
- category: VARCHAR, 产品类别（电子/服装/食品/家居/运动）
- unit_price: DECIMAL(10,2), 标准售价（元）
- supplier: VARCHAR, 供应商名称

表3：customers（客户表，1000行）
- customer_id: VARCHAR, 客户唯一ID
- customer_name: VARCHAR, 客户/公司名称
- city: VARCHAR, 所在城市
- province: VARCHAR, 所在省份
- tier: VARCHAR, 客户等级（A=优质客户, B=普通客户, C=低价值客户）

表4：regions（地区表，20行）
- region_id: VARCHAR, 地区ID
- region_name: VARCHAR, 大区名称（华东/华南/华北/西部/华中/东北）
- province: VARCHAR, 省份

常用JOIN关系：
- orders JOIN products ON orders.product_id = products.product_id
- orders JOIN customers ON orders.customer_id = customers.customer_id
- orders JOIN regions ON orders.province = regions.province

常用查询示例：
- 各大区销售额：SELECT region_name, ROUND(SUM(total_amount),2) as sales FROM orders WHERE status='completed' GROUP BY region_name ORDER BY sales DESC
- 月度趋势：SELECT DATE_TRUNC('month', order_date) as month, ROUND(SUM(total_amount),2) as sales FROM orders WHERE status='completed' GROUP BY month ORDER BY month
- 产品类别占比：SELECT p.category, ROUND(SUM(o.total_amount),2) as sales FROM orders o JOIN products p ON o.product_id=p.product_id WHERE o.status='completed' GROUP BY p.category
"""

def get_relevant_schema(question: str = "") -> str:
    return SCHEMA_DESCRIPTION
