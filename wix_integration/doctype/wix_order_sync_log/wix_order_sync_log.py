import frappe
from frappe.model.document import Document
from frappe.utils import now, flt
import json

class WixOrderSyncLog(Document):
	def validate(self):
		"""Validate order sync log"""
		if not self.created_time:
			self.created_time = now()
	
	def create_sales_order(self):
		"""Create Sales Order from Wix order data"""
		try:
			if self.sales_order:
				frappe.throw("Sales Order already exists for this Wix order")
			
			self.sync_status = "Processing"
			self.save()
			
			# Parse Wix order data
			wix_order = json.loads(self.wix_order_data) if self.wix_order_data else {}
			
			# Get or create customer
			from wix_integration.doctype.wix_customer_mapping.wix_customer_mapping import get_or_create_customer_from_wix
			
			customer = None
			if self.wix_customer_id and wix_order.get('buyerInfo'):
				customer = get_or_create_customer_from_wix(wix_order['buyerInfo'])
			
			if not customer:
				customer = frappe.db.get_single_value("Wix Integration Settings", "default_customer_group") or "Guest Customer"
			
			# Create Sales Order
			settings = frappe.get_single("Wix Integration Settings")
			
			sales_order = frappe.get_doc({
				"doctype": "Sales Order",
				"customer": customer,
				"order_type": "Sales",
				"transaction_date": now().split()[0],
				"delivery_date": now().split()[0],
				"company": frappe.defaults.get_user_default("Company"),
				"currency": wix_order.get('currency', 'USD'),
				"selling_price_list": settings.default_price_list,
				"items": []
			})
			
			# Add order items
			total_amount = 0
			if wix_order.get('lineItems'):
				for line_item in wix_order['lineItems']:
					item_code = self.get_or_create_item_from_wix(line_item)
					if item_code:
						sales_order.append("items", {
							"item_code": item_code,
							"qty": line_item.get('quantity', 1),
							"rate": flt(line_item.get('price', 0)),
							"warehouse": settings.default_warehouse,
							"description": line_item.get('name', '')
						})
						total_amount += flt(line_item.get('price', 0)) * flt(line_item.get('quantity', 1))
			
			# Add shipping charges if any
			if wix_order.get('shippingInfo', {}).get('cost'):
				shipping_cost = flt(wix_order['shippingInfo']['cost'])
				if shipping_cost > 0:
					# Create or get shipping item
					shipping_item = self.get_or_create_shipping_item()
					sales_order.append("items", {
						"item_code": shipping_item,
						"qty": 1,
						"rate": shipping_cost,
						"warehouse": settings.default_warehouse,
						"description": "Shipping Charges"
					})
					total_amount += shipping_cost
			
			# Add taxes if any
			if wix_order.get('tax'):
				tax_amount = flt(wix_order['tax'])
				if tax_amount > 0:
					# Add tax template or manual tax
					sales_order.append("taxes", {
						"charge_type": "Actual",
						"account_head": "Tax - Company",  # This should be configured
						"description": "Tax",
						"tax_amount": tax_amount
					})
			
			sales_order.insert()
			
			# Update sync log
			self.sales_order = sales_order.name
			self.customer = customer
			self.order_total = total_amount
			self.sync_status = "Synced"
			self.last_sync_time = now()
			self.error_log = ""
			self.save()
			
			# Create customer mapping if doesn't exist
			if self.wix_customer_id:
				from wix_integration.doctype.wix_customer_mapping.wix_customer_mapping import create_customer_mapping
				create_customer_mapping(customer, self.wix_customer_id)
			
			return sales_order.name
			
		except Exception as e:
			self.sync_status = "Error"
			self.error_log = str(e)
			self.last_error_time = now()
			self.retry_count = (self.retry_count or 0) + 1
			self.save()
			frappe.log_error(f"Sales Order creation failed for Wix order {self.wix_order_id}: {str(e)}", "Wix Integration")
			raise e
	
	def get_or_create_item_from_wix(self, line_item):
		"""Get or create Frappe item from Wix line item"""
		try:
			# Try to find existing mapping
			product_mapping = frappe.db.get_value(
				"Wix Product Mapping",
				{"wix_product_id": line_item.get('productId')},
				"item_code"
			)
			
			if product_mapping:
				return product_mapping
			
			# Check if auto create is enabled
			settings = frappe.get_single("Wix Integration Settings")
			if not settings.auto_create_items:
				frappe.log_error(f"Auto create items disabled. Product {line_item.get('name')} not found", "Wix Integration")
				return None
			
			# Create new item
			item_code = line_item.get('sku') or f"WIX-{line_item.get('productId', '')}"
			
			if frappe.db.exists("Item", item_code):
				# Use existing item
				return item_code
			
			item_doc = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": line_item.get('name', item_code),
				"description": line_item.get('description', ''),
				"item_group": "Products",  # Default item group
				"stock_uom": "Nos",
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"is_stock_item": 1,
				"include_item_in_manufacturing": 0
			})
			item_doc.insert()
			
			# Create product mapping
			from wix_integration.doctype.wix_product_mapping.wix_product_mapping import create_product_mapping
			create_product_mapping(item_code, line_item.get('productId'))
			
			# Create item price
			if line_item.get('price') and settings.default_price_list:
				frappe.get_doc({
					"doctype": "Item Price",
					"item_code": item_code,
					"price_list": settings.default_price_list,
					"price_list_rate": flt(line_item['price'])
				}).insert()
			
			return item_code
			
		except Exception as e:
			frappe.log_error(f"Item creation failed for Wix product {line_item.get('productId')}: {str(e)}", "Wix Integration")
			return None
	
	def get_or_create_shipping_item(self):
		"""Get or create shipping item"""
		shipping_item = "SHIPPING"
		
		if not frappe.db.exists("Item", shipping_item):
			frappe.get_doc({
				"doctype": "Item",
				"item_code": shipping_item,
				"item_name": "Shipping Charges",
				"item_group": "Services",
				"stock_uom": "Nos",
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0
			}).insert()
		
		return shipping_item
	
	def update_from_wix_webhook(self, webhook_data):
		"""Update order status from Wix webhook"""
		try:
			# Update order details from webhook
			if webhook_data.get('orderNumber'):
				self.wix_order_number = webhook_data['orderNumber']
			
			if webhook_data.get('paymentStatus'):
				self.payment_status = webhook_data['paymentStatus']
			
			if webhook_data.get('fulfillmentStatus'):
				self.fulfillment_status = webhook_data['fulfillmentStatus']
			
			# Update Sales Order status if needed
			if self.sales_order and webhook_data.get('fulfillmentStatus') == 'FULFILLED':
				sales_order = frappe.get_doc("Sales Order", self.sales_order)
				if sales_order.docstatus == 1:  # Submitted
					# Create delivery note if not exists
					self.create_delivery_note()
			
			self.last_sync_time = now()
			self.save()
			
		except Exception as e:
			self.error_log = str(e)
			self.last_error_time = now()
			self.save()
			frappe.log_error(f"Webhook update failed for order {self.wix_order_id}: {str(e)}", "Wix Integration")
	
	def create_delivery_note(self):
		"""Create delivery note from sales order"""
		try:
			if not self.sales_order:
				return
			
			# Check if delivery note already exists
			existing_dn = frappe.db.get_value("Delivery Note Item", {"against_sales_order": self.sales_order}, "parent")
			if existing_dn:
				return existing_dn
			
			sales_order = frappe.get_doc("Sales Order", self.sales_order)
			
			delivery_note = frappe.get_doc({
				"doctype": "Delivery Note",
				"customer": sales_order.customer,
				"posting_date": now().split()[0],
				"company": sales_order.company,
				"items": []
			})
			
			for item in sales_order.items:
				delivery_note.append("items", {
					"item_code": item.item_code,
					"qty": item.qty,
					"rate": item.rate,
					"warehouse": item.warehouse,
					"against_sales_order": sales_order.name,
					"so_detail": item.name
				})
			
			delivery_note.insert()
			delivery_note.submit()
			
			return delivery_note.name
			
		except Exception as e:
			frappe.log_error(f"Delivery note creation failed for order {self.sales_order}: {str(e)}", "Wix Integration")
			return None

@frappe.whitelist()
def create_order_sync_log(wix_order_id, wix_order_data, auto_create=True):
	"""Create a new order sync log"""
	if frappe.db.exists("Wix Order Sync Log", {"wix_order_id": wix_order_id}):
		return frappe.get_doc("Wix Order Sync Log", {"wix_order_id": wix_order_id})
	
	wix_order = json.loads(wix_order_data) if isinstance(wix_order_data, str) else wix_order_data
	
	log = frappe.get_doc({
		"doctype": "Wix Order Sync Log",
		"wix_order_id": wix_order_id,
		"wix_order_number": wix_order.get('orderNumber'),
		"wix_customer_id": wix_order.get('buyerInfo', {}).get('id'),
		"order_total": flt(wix_order.get('totals', {}).get('total')),
		"payment_status": wix_order.get('paymentStatus', 'Pending'),
		"fulfillment_status": wix_order.get('fulfillmentStatus', 'Pending'),
		"order_items_count": len(wix_order.get('lineItems', [])),
		"wix_order_data": json.dumps(wix_order, indent=2)
	})
	log.insert()
	
	if auto_create:
		log.create_sales_order()
	
	return log