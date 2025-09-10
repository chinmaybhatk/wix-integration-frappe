import frappe
from frappe.utils import now, add_days
from wix_integration.utils.wix_client import get_wix_client

def process_pending_orders():
	"""Scheduled task to process pending orders"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		frappe.logger().info("Starting pending orders processing")
		
		# Get pending order logs
		pending_orders = frappe.get_all(
			"Wix Order Sync Log",
			filters={"sync_status": "Pending"},
			fields=["name", "wix_order_id", "retry_count"]
		)
		
		processed_count = 0
		
		for order_data in pending_orders:
			try:
				# Skip if too many retries
				if (order_data.retry_count or 0) >= 3:
					continue
				
				order_log = frappe.get_doc("Wix Order Sync Log", order_data.name)
				sales_order = order_log.create_sales_order()
				
				if sales_order:
					processed_count += 1
					frappe.logger().info(f"Processed pending order: {order_data.wix_order_id}")
				
			except Exception as e:
				frappe.log_error(f"Failed to process pending order {order_data.wix_order_id}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Pending orders processing completed: {processed_count} orders processed")
		
	except Exception as e:
		frappe.log_error(f"Pending orders processing failed: {str(e)}", "Wix Integration")

def sync_all_orders():
	"""Sync all recent orders from Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		frappe.logger().info("Starting order sync from Wix")
		
		# Sync orders from Wix
		from wix_integration.api.orders import sync_orders_from_wix
		result = sync_orders_from_wix()
		
		if result.get('success'):
			frappe.logger().info(f"Order sync completed: {result.get('total_synced')} orders synced")
		else:
			frappe.logger().error(f"Order sync failed: {result.get('message')}")
		
	except Exception as e:
		frappe.log_error(f"Order sync from Wix failed: {str(e)}", "Wix Integration")

def update_order_fulfillment_status():
	"""Update order fulfillment status in Wix based on Frappe delivery notes"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		# Get sales orders with delivery notes that haven't been updated in Wix
		orders_to_update = frappe.db.sql("""
			SELECT DISTINCT 
				wos.name as log_name,
				wos.wix_order_id,
				wos.sales_order,
				wos.fulfillment_status
			FROM `tabWix Order Sync Log` wos
			INNER JOIN `tabDelivery Note Item` dni ON wos.sales_order = dni.against_sales_order
			INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
			WHERE dn.docstatus = 1
			AND wos.fulfillment_status != 'Fulfilled'
			AND wos.sync_status = 'Synced'
		""", as_dict=True)
		
		wix_client = get_wix_client()
		updated_count = 0
		
		for order in orders_to_update:
			try:
				# Update fulfillment status in Wix
				from wix_integration.api.orders import update_wix_fulfillment_status
				result = update_wix_fulfillment_status(order.sales_order, "fulfilled")
				
				if result.get('success'):
					updated_count += 1
					frappe.logger().info(f"Updated fulfillment status for order {order.wix_order_id}")
				
			except Exception as e:
				frappe.log_error(f"Failed to update fulfillment for order {order.wix_order_id}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Order fulfillment update completed: {updated_count} orders updated")
		
	except Exception as e:
		frappe.log_error(f"Order fulfillment update failed: {str(e)}", "Wix Integration")

def sync_tracking_information():
	"""Sync tracking information to Wix for shipped orders"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		# Get delivery notes with tracking info that haven't been synced
		tracking_updates = frappe.db.sql("""
			SELECT DISTINCT
				wos.name as log_name,
				wos.wix_order_id,
				wos.sales_order,
				dn.lr_no as tracking_number,
				dn.transporter_name as carrier
			FROM `tabWix Order Sync Log` wos
			INNER JOIN `tabDelivery Note Item` dni ON wos.sales_order = dni.against_sales_order
			INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
			WHERE dn.docstatus = 1
			AND dn.lr_no IS NOT NULL
			AND dn.lr_no != ''
			AND (wos.tracking_number IS NULL OR wos.tracking_number != dn.lr_no)
		""", as_dict=True)
		
		updated_count = 0
		
		for tracking in tracking_updates:
			try:
				from wix_integration.api.orders import update_tracking_info
				result = update_tracking_info(
					tracking.sales_order,
					tracking.tracking_number,
					tracking.carrier
				)
				
				if result.get('success'):
					updated_count += 1
					frappe.logger().info(f"Updated tracking info for order {tracking.wix_order_id}")
				
			except Exception as e:
				frappe.log_error(f"Failed to update tracking for order {tracking.wix_order_id}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Tracking information sync completed: {updated_count} orders updated")
		
	except Exception as e:
		frappe.log_error(f"Tracking information sync failed: {str(e)}", "Wix Integration")

def cleanup_old_order_logs():
	"""Clean up old order sync logs"""
	try:
		# Delete logs older than 90 days
		cutoff_date = add_days(now(), -90)
		
		old_logs = frappe.get_all(
			"Wix Order Sync Log",
			filters={
				"creation": ["<", cutoff_date],
				"sync_status": ["in", ["Synced", "Cancelled"]]
			},
			fields=["name"]
		)
		
		deleted_count = 0
		for log in old_logs:
			try:
				frappe.delete_doc("Wix Order Sync Log", log.name)
				deleted_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to delete old log {log.name}: {str(e)}", "Wix Integration")
				continue
		
		if deleted_count > 0:
			frappe.logger().info(f"Cleaned up {deleted_count} old order sync logs")
		
	except Exception as e:
		frappe.log_error(f"Order log cleanup failed: {str(e)}", "Wix Integration")

def validate_order_data():
	"""Validate order data consistency between Frappe and Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled:
			return
		
		wix_client = get_wix_client()
		
		# Get recent synced orders
		synced_orders = frappe.get_all(
			"Wix Order Sync Log",
			filters={
				"sync_status": "Synced",
				"creation": [">=", add_days(now(), -7)]
			},
			fields=["name", "wix_order_id", "sales_order", "order_total"]
		)
		
		validation_errors = []
		
		for order_data in synced_orders:
			try:
				if not order_data.sales_order:
					continue
				
				# Get Frappe order data
				sales_order = frappe.get_doc("Sales Order", order_data.sales_order)
				
				# Get Wix order data
				wix_order = wix_client.get_order(order_data.wix_order_id)
				
				if not wix_order:
					validation_errors.append({
						"order_log": order_data.name,
						"error": "Order not found in Wix",
						"wix_order_id": order_data.wix_order_id
					})
					continue
				
				# Validate order total
				wix_total = float(wix_order.get('totals', {}).get('total', 0))
				frappe_total = float(sales_order.grand_total)
				
				if abs(wix_total - frappe_total) > 0.01:  # More than 1 cent difference
					validation_errors.append({
						"order_log": order_data.name,
						"error": f"Total mismatch: Frappe={frappe_total}, Wix={wix_total}",
						"wix_order_id": order_data.wix_order_id
					})
				
				# Validate item count
				wix_items = len(wix_order.get('lineItems', []))
				frappe_items = len(sales_order.items)
				
				if wix_items != frappe_items:
					validation_errors.append({
						"order_log": order_data.name,
						"error": f"Item count mismatch: Frappe={frappe_items}, Wix={wix_items}",
						"wix_order_id": order_data.wix_order_id
					})
				
			except Exception as e:
				validation_errors.append({
					"order_log": order_data.name,
					"error": f"Validation failed: {str(e)}",
					"wix_order_id": order_data.wix_order_id
				})
				continue
		
		if validation_errors:
			frappe.logger().warning(f"Order validation found {len(validation_errors)} errors")
			
			# Create error log
			error_log = frappe.get_doc({
				"doctype": "Error Log",
				"method": "wix_integration.tasks.sync_orders.validate_order_data",
				"error": f"Order validation errors: {validation_errors}"
			})
			error_log.insert()
		else:
			frappe.logger().info("Order validation completed successfully - no errors found")
		
	except Exception as e:
		frappe.log_error(f"Order validation failed: {str(e)}", "Wix Integration")

def sync_payment_status():
	"""Sync payment status between Frappe and Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_orders:
			return
		
		wix_client = get_wix_client()
		
		# Get orders with payment entries that need status update
		paid_orders = frappe.db.sql("""
			SELECT DISTINCT
				wos.name as log_name,
				wos.wix_order_id,
				wos.sales_order,
				wos.payment_status,
				SUM(pe.paid_amount) as total_paid,
				so.grand_total
			FROM `tabWix Order Sync Log` wos
			INNER JOIN `tabSales Order` so ON wos.sales_order = so.name
			LEFT JOIN `tabPayment Entry Reference` per ON so.name = per.reference_name
			LEFT JOIN `tabPayment Entry` pe ON per.parent = pe.name AND pe.docstatus = 1
			WHERE wos.sync_status = 'Synced'
			AND wos.payment_status != 'Paid'
			GROUP BY wos.name, wos.wix_order_id, wos.sales_order, wos.payment_status, so.grand_total
			HAVING total_paid >= so.grand_total
		""", as_dict=True)
		
		updated_count = 0
		
		for order in paid_orders:
			try:
				# Update payment status in order log
				order_log = frappe.get_doc("Wix Order Sync Log", order.log_name)
				order_log.payment_status = "Paid"
				order_log.last_sync_time = now()
				order_log.save()
				
				updated_count += 1
				frappe.logger().info(f"Updated payment status for order {order.wix_order_id}")
				
			except Exception as e:
				frappe.log_error(f"Failed to update payment status for order {order.wix_order_id}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Payment status sync completed: {updated_count} orders updated")
		
	except Exception as e:
		frappe.log_error(f"Payment status sync failed: {str(e)}", "Wix Integration")

def generate_order_summary_report():
	"""Generate daily order summary report"""
	try:
		today = now().split()[0]
		
		# Get today's order statistics
		order_stats = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_orders,
				SUM(order_total) as total_value,
				COUNT(CASE WHEN sync_status = 'Synced' THEN 1 END) as synced_orders,
				COUNT(CASE WHEN sync_status = 'Error' THEN 1 END) as error_orders,
				COUNT(CASE WHEN sync_status = 'Pending' THEN 1 END) as pending_orders
			FROM `tabWix Order Sync Log`
			WHERE DATE(created_time) = %s
		""", (today,), as_dict=True)[0]
		
		if order_stats.total_orders > 0:
			# Create summary report
			report = f"""
Daily Order Summary - {today}
================================

Total Orders: {order_stats.total_orders}
Total Value: ${order_stats.total_value or 0:,.2f}
Synced Orders: {order_stats.synced_orders}
Error Orders: {order_stats.error_orders}
Pending Orders: {order_stats.pending_orders}

Sync Rate: {(order_stats.synced_orders / order_stats.total_orders * 100):.1f}%
"""
			
			frappe.logger().info(f"Daily order summary: {order_stats.total_orders} orders, ${order_stats.total_value or 0:,.2f} value")
			
			# Send to system managers if there are errors
			if order_stats.error_orders > 0:
				from wix_integration.tasks.sync_inventory import get_system_managers
				
				frappe.sendmail(
					recipients=get_system_managers(),
					subject=f"Wix Integration - Daily Order Summary ({today})",
					message=report
				)
		
	except Exception as e:
		frappe.log_error(f"Order summary report failed: {str(e)}", "Wix Integration")