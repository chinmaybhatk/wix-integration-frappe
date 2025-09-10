import frappe
from frappe.utils import now
from wix_integration.utils.wix_client import get_wix_client
import json

@frappe.whitelist()
def update_order_status_to_wix(doc, method=None):
	"""Update order status in Wix when Sales Order is submitted"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		# Check if this order came from Wix
		order_log = frappe.db.get_value("Wix Order Sync Log", {"sales_order": doc.name}, "wix_order_id")
		
		if order_log:
			# This order came from Wix, update fulfillment status
			update_wix_fulfillment_status(doc.name, "processing")
			
	except Exception as e:
		frappe.log_error(f"Order status update to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def cancel_order_in_wix(doc, method=None):
	"""Cancel order in Wix when Sales Order is cancelled"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		# Check if this order came from Wix
		order_log = frappe.db.get_value("Wix Order Sync Log", {"sales_order": doc.name}, "wix_order_id")
		
		if order_log:
			wix_client = get_wix_client()
			result = wix_client.cancel_order(order_log)
			
			if result:
				frappe.logger().info(f"Order {doc.name} cancelled in Wix")
			else:
				frappe.logger().error(f"Failed to cancel order {doc.name} in Wix")
				
	except Exception as e:
		frappe.log_error(f"Order cancellation in Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def process_wix_order(wix_order_data):
	"""Process incoming Wix order and create Sales Order"""
	try:
		if isinstance(wix_order_data, str):
			wix_order_data = json.loads(wix_order_data)
		
		wix_order_id = wix_order_data.get('id')
		
		if not wix_order_id:
			return {"success": False, "message": "Invalid order data - missing order ID"}
		
		# Check if order already processed
		existing_log = frappe.db.get_value("Wix Order Sync Log", {"wix_order_id": wix_order_id}, "name")
		
		if existing_log:
			return {"success": True, "message": "Order already processed", "log": existing_log}
		
		# Create order sync log
		from wix_integration.doctype.wix_order_sync_log.wix_order_sync_log import create_order_sync_log
		
		log = create_order_sync_log(wix_order_id, wix_order_data, auto_create=True)
		
		return {
			"success": True,
			"message": "Order processed successfully",
			"log": log.name,
			"sales_order": log.sales_order
		}
		
	except Exception as e:
		frappe.log_error(f"Wix order processing failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_orders_from_wix(status=None, limit=50):
	"""Sync orders from Wix to Frappe"""
	try:
		wix_client = get_wix_client()
		offset = 0
		total_synced = 0
		
		while True:
			response = wix_client.get_orders(limit=limit, offset=offset, status=status)
			
			if not response or not response.get('orders'):
				break
			
			orders = response['orders']
			
			for order in orders:
				try:
					result = process_wix_order(order)
					if result.get('success'):
						total_synced += 1
				except Exception as e:
					frappe.log_error(f"Failed to sync order {order.get('id')}: {str(e)}", "Wix Integration")
					continue
			
			# Check if we have more orders
			if len(orders) < limit:
				break
			
			offset += limit
		
		return {"success": True, "total_synced": total_synced}
		
	except Exception as e:
		frappe.log_error(f"Orders sync from Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def update_wix_fulfillment_status(sales_order, status):
	"""Update fulfillment status in Wix for a Sales Order"""
	try:
		# Get Wix order ID
		order_log = frappe.get_value("Wix Order Sync Log", {"sales_order": sales_order}, ["wix_order_id", "name"])
		
		if not order_log:
			return {"success": False, "message": "No Wix order mapping found"}
		
		wix_order_id, log_name = order_log
		
		wix_client = get_wix_client()
		
		# Map Frappe status to Wix status
		status_mapping = {
			"draft": "pending",
			"processing": "processing",
			"delivered": "fulfilled",
			"cancelled": "cancelled"
		}
		
		wix_status = status_mapping.get(status.lower(), status.lower())
		
		# Update fulfillment in Wix
		fulfillment_data = {
			"fulfillment": {
				"status": wix_status
			}
		}
		
		result = wix_client.update_order_fulfillment(wix_order_id, fulfillment_data)
		
		if result:
			# Update sync log
			log_doc = frappe.get_doc("Wix Order Sync Log", log_name)
			log_doc.fulfillment_status = wix_status.title()
			log_doc.last_sync_time = now()
			log_doc.save()
			
			return {"success": True, "message": "Fulfillment status updated in Wix"}
		else:
			return {"success": False, "message": "Failed to update fulfillment status in Wix"}
			
	except Exception as e:
		frappe.log_error(f"Fulfillment status update failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def create_delivery_note_from_wix_order(sales_order):
	"""Create delivery note from Sales Order for Wix orders"""
	try:
		# Get order log
		order_log = frappe.get_value("Wix Order Sync Log", {"sales_order": sales_order}, "name")
		
		if not order_log:
			return {"success": False, "message": "No Wix order mapping found"}
		
		log_doc = frappe.get_doc("Wix Order Sync Log", order_log)
		delivery_note = log_doc.create_delivery_note()
		
		if delivery_note:
			# Update Wix fulfillment status
			update_wix_fulfillment_status(sales_order, "fulfilled")
			
			return {
				"success": True,
				"message": "Delivery note created and Wix updated",
				"delivery_note": delivery_note
			}
		else:
			return {"success": False, "message": "Failed to create delivery note"}
			
	except Exception as e:
		frappe.log_error(f"Delivery note creation failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def get_order_sync_status():
	"""Get status of order synchronization"""
	try:
		total_orders = frappe.db.count("Wix Order Sync Log")
		synced_orders = frappe.db.count("Wix Order Sync Log", {"sync_status": "Synced"})
		error_orders = frappe.db.count("Wix Order Sync Log", {"sync_status": "Error"})
		pending_orders = frappe.db.count("Wix Order Sync Log", {"sync_status": "Pending"})
		processing_orders = frappe.db.count("Wix Order Sync Log", {"sync_status": "Processing"})
		
		# Get recent orders (last 24 hours)
		recent_orders = frappe.db.count("Wix Order Sync Log", {
			"created_time": [">=", frappe.utils.add_days(now(), -1)]
		})
		
		return {
			"total": total_orders,
			"synced": synced_orders,
			"errors": error_orders,
			"pending": pending_orders,
			"processing": processing_orders,
			"recent": recent_orders,
			"sync_rate": (synced_orders / total_orders * 100) if total_orders > 0 else 0
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get order sync status: {str(e)}", "Wix Integration")
		return {"error": str(e)}

@frappe.whitelist()
def retry_failed_order_syncs():
	"""Retry failed order synchronizations"""
	try:
		failed_orders = frappe.get_all(
			"Wix Order Sync Log",
			filters={"sync_status": "Error"},
			fields=["name", "wix_order_id", "wix_order_data"]
		)
		
		retry_count = 0
		success_count = 0
		
		for order_data in failed_orders:
			try:
				order_log = frappe.get_doc("Wix Order Sync Log", order_data.name)
				
				# Try to create sales order again
				sales_order = order_log.create_sales_order()
				
				if sales_order:
					success_count += 1
				retry_count += 1
				
			except Exception as e:
				frappe.log_error(f"Retry order sync failed for {order_data.name}: {str(e)}", "Wix Integration")
				continue
		
		return {
			"success": True,
			"retried": retry_count,
			"succeeded": success_count,
			"failed": retry_count - success_count
		}
		
	except Exception as e:
		frappe.log_error(f"Retry failed order syncs failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def update_tracking_info(sales_order, tracking_number, carrier=None):
	"""Update tracking information in Wix for an order"""
	try:
		# Get Wix order ID
		order_log = frappe.get_value("Wix Order Sync Log", {"sales_order": sales_order}, ["wix_order_id", "name"])
		
		if not order_log:
			return {"success": False, "message": "No Wix order mapping found"}
		
		wix_order_id, log_name = order_log
		
		wix_client = get_wix_client()
		
		# Update tracking info in Wix
		tracking_data = {
			"fulfillment": {
				"trackingInfo": {
					"trackingNumber": tracking_number,
					"shippingProvider": carrier or "Other"
				}
			}
		}
		
		result = wix_client.update_order_fulfillment(wix_order_id, tracking_data)
		
		if result:
			# Update sync log
			log_doc = frappe.get_doc("Wix Order Sync Log", log_name)
			log_doc.tracking_number = tracking_number
			log_doc.last_sync_time = now()
			log_doc.save()
			
			return {"success": True, "message": "Tracking information updated in Wix"}
		else:
			return {"success": False, "message": "Failed to update tracking information in Wix"}
			
	except Exception as e:
		frappe.log_error(f"Tracking info update failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}