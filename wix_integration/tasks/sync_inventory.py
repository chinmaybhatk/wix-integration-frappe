import frappe
from frappe.utils import now, flt
from wix_integration.utils.wix_client import get_wix_client

def sync_all_inventory():
	"""Scheduled task to sync inventory levels"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return
		
		frappe.logger().info("Starting scheduled inventory sync")
		
		# Get all product mappings
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={"sync_status": ["in", ["Synced", "Conflict"]]},
			fields=["name", "item_code", "wix_product_id", "wix_variant_id", "sync_direction"]
		)
		
		wix_client = get_wix_client()
		updated_count = 0
		
		for mapping_data in mappings:
			try:
				mapping = frappe.get_doc("Wix Product Mapping", mapping_data.name)
				
				# Get current Frappe stock
				current_stock = get_item_stock_qty(mapping.item_code)
				
				# Update in Wix if sync direction allows
				if mapping.sync_direction in ["Bidirectional", "Frappe to Wix"]:
					result = wix_client.update_inventory(
						mapping.wix_product_id,
						mapping.wix_variant_id,
						current_stock
					)
					
					if result:
						mapping.frappe_stock_qty = current_stock
						mapping.last_sync_time = now()
						mapping.save()
						updated_count += 1
					else:
						frappe.logger().error(f"Failed to update inventory for {mapping.item_code}")
				
			except Exception as e:
				frappe.log_error(f"Inventory sync failed for {mapping_data.item_code}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Inventory sync completed: {updated_count} products updated")
		
	except Exception as e:
		frappe.log_error(f"Scheduled inventory sync failed: {str(e)}", "Wix Integration")

def get_item_stock_qty(item_code, warehouse=None):
	"""Get current stock quantity for an item"""
	try:
		if not warehouse:
			settings = frappe.get_single("Wix Integration Settings")
			warehouse = settings.default_warehouse
		
		if not warehouse:
			return 0
		
		stock_qty = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"actual_qty"
		) or 0
		
		return max(0, flt(stock_qty))  # Don't sync negative inventory
		
	except Exception as e:
		frappe.log_error(f"Failed to get stock qty for {item_code}: {str(e)}", "Wix Integration")
		return 0

def sync_inventory_from_wix():
	"""Sync inventory levels from Wix to Frappe"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return
		
		wix_client = get_wix_client()
		
		# Get all product mappings
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={
				"sync_status": ["in", ["Synced", "Conflict"]],
				"sync_direction": ["in", ["Bidirectional", "Wix to Frappe"]]
			},
			fields=["name", "item_code", "wix_product_id", "wix_variant_id"]
		)
		
		updated_count = 0
		
		for mapping_data in mappings:
			try:
				# Get current inventory from Wix
				wix_product = wix_client.get_product(mapping_data.wix_product_id)
				
				if not wix_product:
					continue
				
				inventory_data = wix_product.get('inventory', {})
				if not inventory_data.get('trackQuantity'):
					continue
				
				wix_qty = flt(inventory_data.get('quantity', 0))
				frappe_qty = get_item_stock_qty(mapping_data.item_code)
				
				# Update Frappe inventory if different
				if abs(wix_qty - frappe_qty) > 0:
					success = update_frappe_inventory(mapping_data.item_code, wix_qty)
					if success:
						updated_count += 1
				
			except Exception as e:
				frappe.log_error(f"Inventory sync from Wix failed for {mapping_data.item_code}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Inventory sync from Wix completed: {updated_count} products updated")
		
	except Exception as e:
		frappe.log_error(f"Inventory sync from Wix failed: {str(e)}", "Wix Integration")

def update_frappe_inventory(item_code, new_qty, warehouse=None):
	"""Update Frappe inventory using Stock Reconciliation"""
	try:
		if not warehouse:
			settings = frappe.get_single("Wix Integration Settings")
			warehouse = settings.default_warehouse
		
		if not warehouse:
			frappe.logger().error(f"No warehouse configured for inventory update of {item_code}")
			return False
		
		# Get current valuation rate
		valuation_rate = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"valuation_rate"
		) or 0
		
		# Create stock reconciliation
		stock_recon = frappe.get_doc({
			"doctype": "Stock Reconciliation",
			"posting_date": now().split()[0],
			"posting_time": now().split()[1],
			"company": frappe.defaults.get_user_default("Company"),
			"purpose": "Stock Reconciliation",
			"items": [{
				"item_code": item_code,
				"warehouse": warehouse,
				"qty": new_qty,
				"valuation_rate": valuation_rate
			}]
		})
		
		stock_recon._from_wix_sync = True  # Flag to prevent sync loop
		stock_recon.insert()
		stock_recon.submit()
		
		frappe.logger().info(f"Updated inventory for {item_code}: {new_qty}")
		return True
		
	except Exception as e:
		frappe.log_error(f"Failed to update Frappe inventory for {item_code}: {str(e)}", "Wix Integration")
		return False

def check_low_stock_alerts():
	"""Check for low stock items and send alerts"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled:
			return
		
		# Get items with low stock
		low_stock_items = frappe.db.sql("""
			SELECT 
				i.item_code,
				i.item_name,
				b.actual_qty,
				COALESCE(ir.warehouse_reorder_level, 0) as reorder_level
			FROM `tabItem` i
			INNER JOIN `tabBin` b ON i.item_code = b.item_code
			LEFT JOIN `tabItem Reorder` ir ON i.item_code = ir.parent AND b.warehouse = ir.warehouse
			INNER JOIN `tabWix Product Mapping` wpm ON i.item_code = wpm.item_code
			WHERE i.is_sales_item = 1 
			AND i.disabled = 0
			AND b.actual_qty <= COALESCE(ir.warehouse_reorder_level, 5)
			AND wpm.sync_status = 'Synced'
		""", as_dict=True)
		
		if low_stock_items:
			# Send notification
			message = "Low Stock Alert for Wix Integration:\n\n"
			for item in low_stock_items:
				message += f"• {item.item_name} ({item.item_code}): {item.actual_qty} remaining (Reorder level: {item.reorder_level})\n"
			
			# Send email to system managers
			frappe.sendmail(
				recipients=get_system_managers(),
				subject="Wix Integration - Low Stock Alert",
				message=message
			)
			
			frappe.logger().info(f"Low stock alert sent for {len(low_stock_items)} items")
		
	except Exception as e:
		frappe.log_error(f"Low stock alert check failed: {str(e)}", "Wix Integration")

def get_system_managers():
	"""Get email addresses of system managers"""
	try:
		managers = frappe.get_all(
			"Has Role",
			filters={"role": "System Manager"},
			fields=["parent"]
		)
		
		emails = []
		for manager in managers:
			email = frappe.db.get_value("User", manager.parent, "email")
			if email:
				emails.append(email)
		
		return emails
		
	except Exception as e:
		frappe.log_error(f"Failed to get system managers: {str(e)}", "Wix Integration")
		return []

def bulk_inventory_update():
	"""Bulk update inventory for all mapped products"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return
		
		wix_client = get_wix_client()
		
		# Get all active mappings
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={
				"sync_status": "Synced",
				"sync_direction": ["in", ["Bidirectional", "Frappe to Wix"]]
			},
			fields=["item_code", "wix_product_id", "wix_variant_id"]
		)
		
		# Prepare bulk update data
		inventory_updates = []
		for mapping in mappings:
			current_stock = get_item_stock_qty(mapping.item_code)
			inventory_updates.append({
				"product_id": mapping.wix_product_id,
				"variant_id": mapping.wix_variant_id,
				"quantity": current_stock
			})
		
		# Execute bulk update
		if inventory_updates:
			result = wix_client.bulk_update_inventory(inventory_updates)
			
			frappe.logger().info(f"Bulk inventory update completed: {result.get('success_count')} successful, {result.get('error_count')} errors")
		
	except Exception as e:
		frappe.log_error(f"Bulk inventory update failed: {str(e)}", "Wix Integration")

def sync_reserved_stock():
	"""Sync reserved stock (stock in pending orders) to Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return
		
		wix_client = get_wix_client()
		
		# Get reserved stock for each item
		reserved_stock_data = frappe.db.sql("""
			SELECT 
				soi.item_code,
				SUM(soi.qty - soi.delivered_qty) as reserved_qty
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON soi.parent = so.name
			WHERE so.docstatus = 1 
			AND so.status NOT IN ('Completed', 'Cancelled', 'Closed')
			AND soi.delivered_qty < soi.qty
			GROUP BY soi.item_code
		""", as_dict=True)
		
		for item_data in reserved_stock_data:
			try:
				# Get mapping
				mapping = frappe.db.get_value(
					"Wix Product Mapping",
					{"item_code": item_data.item_code},
					["wix_product_id", "wix_variant_id"]
				)
				
				if mapping:
					wix_product_id, wix_variant_id = mapping
					
					# Calculate available stock (actual - reserved)
					actual_stock = get_item_stock_qty(item_data.item_code)
					available_stock = max(0, actual_stock - flt(item_data.reserved_qty))
					
					# Update Wix with available stock
					result = wix_client.update_inventory(wix_product_id, wix_variant_id, available_stock)
					
					if result:
						frappe.logger().info(f"Updated available stock for {item_data.item_code}: {available_stock} (Reserved: {item_data.reserved_qty})")
				
			except Exception as e:
				frappe.log_error(f"Reserved stock sync failed for {item_data.item_code}: {str(e)}", "Wix Integration")
				continue
		
	except Exception as e:
		frappe.log_error(f"Reserved stock sync failed: {str(e)}", "Wix Integration")

def inventory_variance_report():
	"""Generate inventory variance report between Frappe and Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled:
			return
		
		wix_client = get_wix_client()
		variances = []
		
		# Get all active mappings
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={"sync_status": "Synced"},
			fields=["name", "item_code", "wix_product_id", "wix_variant_id"]
		)
		
		for mapping_data in mappings:
			try:
				# Get Frappe stock
				frappe_stock = get_item_stock_qty(mapping_data.item_code)
				
				# Get Wix stock
				wix_product = wix_client.get_product(mapping_data.wix_product_id)
				wix_stock = 0
				
				if wix_product and wix_product.get('inventory'):
					wix_stock = flt(wix_product['inventory'].get('quantity', 0))
				
				# Calculate variance
				variance = frappe_stock - wix_stock
				
				if abs(variance) > 0:
					variances.append({
						"item_code": mapping_data.item_code,
						"frappe_stock": frappe_stock,
						"wix_stock": wix_stock,
						"variance": variance
					})
				
			except Exception as e:
				frappe.log_error(f"Variance calculation failed for {mapping_data.item_code}: {str(e)}", "Wix Integration")
				continue
		
		if variances:
			# Create variance report
			report_content = "Inventory Variance Report (Frappe vs Wix)\n"
			report_content += "=" * 50 + "\n\n"
			
			for item in variances:
				report_content += f"Item: {item['item_code']}\n"
				report_content += f"  Frappe Stock: {item['frappe_stock']}\n"
				report_content += f"  Wix Stock: {item['wix_stock']}\n"
				report_content += f"  Variance: {item['variance']}\n\n"
			
			# Save to file or send email
			frappe.logger().info(f"Inventory variance report generated: {len(variances)} items with variances")
			
			return variances
		else:
			frappe.logger().info("No inventory variances found")
			return []
		
	except Exception as e:
		frappe.log_error(f"Inventory variance report failed: {str(e)}", "Wix Integration")
		return []