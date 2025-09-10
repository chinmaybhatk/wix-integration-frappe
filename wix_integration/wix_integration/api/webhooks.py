import frappe
from frappe.utils import now
from wix_integration.utils.wix_client import get_wix_client
import json

@frappe.whitelist(allow_guest=True)
def handle_wix_webhook():
	"""Handle incoming Wix webhooks"""
	try:
		# Get webhook data
		data = frappe.local.form_dict
		
		# Validate webhook signature
		signature = frappe.get_request_header("X-Wix-Webhook-Signature")
		payload = frappe.request.get_data()
		
		wix_client = get_wix_client()
		if not wix_client.validate_webhook_signature(payload, signature):
			frappe.throw("Invalid webhook signature", frappe.PermissionError)
		
		# Parse webhook data
		webhook_data = json.loads(payload.decode('utf-8')) if payload else data
		event_type = webhook_data.get('eventType')
		entity_id = webhook_data.get('entityId')
		
		frappe.logger().info(f"Received Wix webhook: {event_type} for entity {entity_id}")
		
		# Process webhook based on event type
		if event_type in ['orders/created', 'orders/updated']:
			return handle_order_webhook(webhook_data)
		elif event_type in ['products/created', 'products/updated', 'products/deleted']:
			return handle_product_webhook(webhook_data)
		elif event_type in ['customers/created', 'customers/updated']:
			return handle_customer_webhook(webhook_data)
		elif event_type in ['inventory/updated']:
			return handle_inventory_webhook(webhook_data)
		else:
			frappe.logger().info(f"Unhandled webhook event type: {event_type}")
			return {"success": True, "message": "Event type not handled"}
		
	except Exception as e:
		frappe.log_error(f"Webhook processing failed: {str(e)}", "Wix Integration")
		frappe.throw(f"Webhook processing failed: {str(e)}")

def handle_order_webhook(webhook_data):
	"""Handle order-related webhooks"""
	try:
		event_type = webhook_data.get('eventType')
		entity_id = webhook_data.get('entityId')
		
		if event_type == 'orders/created':
			# New order created in Wix
			return process_new_order_webhook(entity_id, webhook_data)
		elif event_type == 'orders/updated':
			# Order updated in Wix
			return process_order_update_webhook(entity_id, webhook_data)
		
		return {"success": True, "message": "Order webhook processed"}
		
	except Exception as e:
		frappe.log_error(f"Order webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_new_order_webhook(order_id, webhook_data):
	"""Process new order webhook"""
	try:
		# Check if order already exists
		existing_log = frappe.db.get_value("Wix Order Sync Log", {"wix_order_id": order_id}, "name")
		
		if existing_log:
			return {"success": True, "message": "Order already processed"}
		
		# Get full order data from Wix
		wix_client = get_wix_client()
		order_data = wix_client.get_order(order_id)
		
		if not order_data:
			return {"success": False, "message": "Could not fetch order data from Wix"}
		
		# Process the order
		from wix_integration.api.orders import process_wix_order
		result = process_wix_order(order_data)
		
		return result
		
	except Exception as e:
		frappe.log_error(f"New order webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_order_update_webhook(order_id, webhook_data):
	"""Process order update webhook"""
	try:
		# Find existing order log
		order_log = frappe.db.get_value("Wix Order Sync Log", {"wix_order_id": order_id}, "name")
		
		if not order_log:
			# Order not in our system, fetch and create
			return process_new_order_webhook(order_id, webhook_data)
		
		# Update order log with webhook data
		log_doc = frappe.get_doc("Wix Order Sync Log", order_log)
		log_doc.update_from_wix_webhook(webhook_data)
		
		return {"success": True, "message": "Order updated from webhook"}
		
	except Exception as e:
		frappe.log_error(f"Order update webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def handle_product_webhook(webhook_data):
	"""Handle product-related webhooks"""
	try:
		event_type = webhook_data.get('eventType')
		entity_id = webhook_data.get('entityId')
		
		if event_type == 'products/created':
			return process_product_created_webhook(entity_id, webhook_data)
		elif event_type == 'products/updated':
			return process_product_updated_webhook(entity_id, webhook_data)
		elif event_type == 'products/deleted':
			return process_product_deleted_webhook(entity_id, webhook_data)
		
		return {"success": True, "message": "Product webhook processed"}
		
	except Exception as e:
		frappe.log_error(f"Product webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_product_created_webhook(product_id, webhook_data):
	"""Process product created webhook"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return {"success": True, "message": "Product sync disabled"}
		
		# Check if product mapping already exists
		existing_mapping = frappe.db.get_value("Wix Product Mapping", {"wix_product_id": product_id}, "name")
		
		if existing_mapping:
			return {"success": True, "message": "Product mapping already exists"}
		
		# Get product data from Wix and create item
		from wix_integration.api.products import sync_product_from_wix
		result = sync_product_from_wix(product_id)
		
		return result
		
	except Exception as e:
		frappe.log_error(f"Product created webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_product_updated_webhook(product_id, webhook_data):
	"""Process product updated webhook"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return {"success": True, "message": "Product sync disabled"}
		
		# Find existing mapping
		mapping = frappe.db.get_value("Wix Product Mapping", {"wix_product_id": product_id}, "name")
		
		if mapping:
			# Update existing product
			mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
			success = mapping_doc.sync_from_wix()
			
			return {"success": success, "message": "Product updated from Wix"}
		else:
			# Create new product if auto-create is enabled
			if settings.auto_create_items:
				from wix_integration.api.products import sync_product_from_wix
				return sync_product_from_wix(product_id)
			else:
				return {"success": True, "message": "Auto-create disabled, product not synced"}
		
	except Exception as e:
		frappe.log_error(f"Product updated webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_product_deleted_webhook(product_id, webhook_data):
	"""Process product deleted webhook"""
	try:
		# Find existing mapping
		mapping = frappe.db.get_value("Wix Product Mapping", {"wix_product_id": product_id}, "name")
		
		if mapping:
			mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
			
			# Mark as deleted or disable the item
			if mapping_doc.item_code:
				item_doc = frappe.get_doc("Item", mapping_doc.item_code)
				item_doc.disabled = 1
				item_doc._from_wix_sync = True  # Prevent sync loop
				item_doc.save()
			
			# Delete the mapping
			mapping_doc.delete()
			
			return {"success": True, "message": "Product deleted and item disabled"}
		else:
			return {"success": True, "message": "Product mapping not found"}
		
	except Exception as e:
		frappe.log_error(f"Product deleted webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def handle_customer_webhook(webhook_data):
	"""Handle customer-related webhooks"""
	try:
		event_type = webhook_data.get('eventType')
		entity_id = webhook_data.get('entityId')
		
		if event_type == 'customers/created':
			return process_customer_created_webhook(entity_id, webhook_data)
		elif event_type == 'customers/updated':
			return process_customer_updated_webhook(entity_id, webhook_data)
		
		return {"success": True, "message": "Customer webhook processed"}
		
	except Exception as e:
		frappe.log_error(f"Customer webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_customer_created_webhook(customer_id, webhook_data):
	"""Process customer created webhook"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_customers:
			return {"success": True, "message": "Customer sync disabled"}
		
		# Check if customer mapping already exists
		existing_mapping = frappe.db.get_value("Wix Customer Mapping", {"wix_customer_id": customer_id}, "name")
		
		if existing_mapping:
			return {"success": True, "message": "Customer mapping already exists"}
		
		# Get customer data from Wix and create customer
		from wix_integration.api.customers import sync_customer_from_wix
		result = sync_customer_from_wix(customer_id)
		
		return result
		
	except Exception as e:
		frappe.log_error(f"Customer created webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def process_customer_updated_webhook(customer_id, webhook_data):
	"""Process customer updated webhook"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_customers:
			return {"success": True, "message": "Customer sync disabled"}
		
		# Find existing mapping
		mapping = frappe.db.get_value("Wix Customer Mapping", {"wix_customer_id": customer_id}, "name")
		
		if mapping:
			# Update existing customer
			mapping_doc = frappe.get_doc("Wix Customer Mapping", mapping)
			success = mapping_doc.sync_from_wix()
			
			return {"success": success, "message": "Customer updated from Wix"}
		else:
			# Create new customer if auto-create is enabled
			if settings.auto_create_customers:
				from wix_integration.api.customers import sync_customer_from_wix
				return sync_customer_from_wix(customer_id)
			else:
				return {"success": True, "message": "Auto-create disabled, customer not synced"}
		
	except Exception as e:
		frappe.log_error(f"Customer updated webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def handle_inventory_webhook(webhook_data):
	"""Handle inventory-related webhooks"""
	try:
		entity_id = webhook_data.get('entityId')  # This would be product ID
		
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return {"success": True, "message": "Inventory sync disabled"}
		
		# Find product mapping
		mapping = frappe.db.get_value("Wix Product Mapping", {"wix_product_id": entity_id}, "name")
		
		if mapping:
			# Get updated inventory from Wix
			wix_client = get_wix_client()
			product_data = wix_client.get_product(entity_id)
			
			if product_data and product_data.get('inventory'):
				inventory = product_data['inventory']
				quantity = inventory.get('quantity', 0)
				
				# Update Frappe inventory
				mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
				if mapping_doc.item_code and settings.default_warehouse:
					
					# Create stock reconciliation to update inventory
					stock_recon = frappe.get_doc({
						"doctype": "Stock Reconciliation",
						"posting_date": now().split()[0],
						"posting_time": now().split()[1],
						"company": frappe.defaults.get_user_default("Company"),
						"items": [{
							"item_code": mapping_doc.item_code,
							"warehouse": settings.default_warehouse,
							"qty": quantity,
							"valuation_rate": 0  # Will be calculated
						}]
					})
					stock_recon._from_wix_sync = True  # Prevent sync loop
					stock_recon.insert()
					stock_recon.submit()
					
					return {"success": True, "message": f"Inventory updated for {mapping_doc.item_code}"}
			
		return {"success": True, "message": "Inventory webhook processed"}
		
	except Exception as e:
		frappe.log_error(f"Inventory webhook processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def test_webhook_endpoint():
	"""Test endpoint for webhook configuration"""
	return {
		"success": True,
		"message": "Webhook endpoint is working",
		"timestamp": now()
	}

@frappe.whitelist()
def get_webhook_logs(limit=50):
	"""Get recent webhook processing logs"""
	try:
		# Get recent error logs related to webhooks
		logs = frappe.get_all(
			"Error Log",
			filters={
				"error": ["like", "%webhook%"],
				"creation": [">=", frappe.utils.add_days(now(), -7)]
			},
			fields=["name", "creation", "error", "method"],
			order_by="creation desc",
			limit=limit
		)
		
		return {"success": True, "logs": logs}
		
	except Exception as e:
		frappe.log_error(f"Failed to get webhook logs: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def configure_wix_webhooks():
	"""Configure webhooks in Wix (requires manual setup in Wix dashboard)"""
	try:
		# Get site URL for webhook endpoints
		site_url = frappe.utils.get_url()
		webhook_url = f"{site_url}/api/method/wix_integration.api.webhooks.handle_wix_webhook"
		
		webhook_config = {
			"endpoint_url": webhook_url,
			"events": [
				"orders/created",
				"orders/updated", 
				"products/created",
				"products/updated",
				"products/deleted",
				"customers/created",
				"customers/updated",
				"inventory/updated"
			],
			"instructions": [
				"1. Go to your Wix Developer Dashboard",
				"2. Navigate to Webhooks section",
				"3. Add a new webhook with the endpoint URL above",
				"4. Select the events you want to monitor",
				"5. Copy the webhook secret and add it to Wix Integration Settings"
			]
		}
		
		return {"success": True, "config": webhook_config}
		
	except Exception as e:
		frappe.log_error(f"Webhook configuration failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}