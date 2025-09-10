import frappe
from frappe.utils import now
from wix_integration.utils.wix_client import get_wix_client

def sync_all_products():
	"""Scheduled task to sync all products"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return
		
		frappe.logger().info("Starting scheduled product sync")
		
		# Sync products from Wix to Frappe
		from wix_integration.api.products import sync_all_products_from_wix
		result = sync_all_products_from_wix()
		
		if result.get('success'):
			frappe.logger().info(f"Product sync completed: {result.get('total_synced')} products synced")
		else:
			frappe.logger().error(f"Product sync failed: {result.get('message')}")
		
		# Update last sync time
		settings.last_sync_time = now()
		settings.save()
		
	except Exception as e:
		frappe.log_error(f"Scheduled product sync failed: {str(e)}", "Wix Integration")

def full_product_sync():
	"""Full bidirectional product synchronization"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return
		
		frappe.logger().info("Starting full product sync")
		
		# Sync from Wix to Frappe
		from wix_integration.api.products import sync_all_products_from_wix
		wix_result = sync_all_products_from_wix()
		
		# Sync from Frappe to Wix
		frappe_result = sync_frappe_products_to_wix()
		
		frappe.logger().info(f"Full product sync completed: Wix->Frappe: {wix_result.get('total_synced', 0)}, Frappe->Wix: {frappe_result.get('total_synced', 0)}")
		
	except Exception as e:
		frappe.log_error(f"Full product sync failed: {str(e)}", "Wix Integration")

def sync_frappe_products_to_wix():
	"""Sync all Frappe products to Wix"""
	try:
		wix_client = get_wix_client()
		
		# Get all items that should be synced
		items = frappe.get_all(
			"Item",
			filters={"is_sales_item": 1, "disabled": 0},
			fields=["item_code", "item_name"]
		)
		
		total_synced = 0
		
		for item in items:
			try:
				# Check if mapping exists
				mapping = frappe.db.get_value("Wix Product Mapping", {"item_code": item.item_code}, "name")
				
				if mapping:
					# Update existing mapping
					mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
					if mapping_doc.sync_direction in ["Bidirectional", "Frappe to Wix"]:
						success = mapping_doc.sync_to_wix()
						if success:
							total_synced += 1
				else:
					# Create new product in Wix
					result = wix_client.sync_product_from_frappe(item.item_code)
					if result:
						total_synced += 1
						
			except Exception as e:
				frappe.log_error(f"Failed to sync item {item.item_code} to Wix: {str(e)}", "Wix Integration")
				continue
		
		return {"success": True, "total_synced": total_synced}
		
	except Exception as e:
		frappe.log_error(f"Frappe to Wix product sync failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def sync_product_prices():
	"""Sync product prices between Frappe and Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return
		
		# Get all product mappings with price differences
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={"sync_status": ["in", ["Synced", "Conflict"]]},
			fields=["name", "item_code", "wix_product_id", "frappe_price", "wix_price", "sync_direction"]
		)
		
		wix_client = get_wix_client()
		updated_count = 0
		
		for mapping_data in mappings:
			try:
				mapping = frappe.get_doc("Wix Product Mapping", mapping_data.name)
				
				# Calculate current prices
				mapping.calculate_differences()
				
				# Check if price sync is needed
				if abs(mapping.price_difference or 0) > 0.01:  # More than 1 cent difference
					
					if mapping.sync_direction in ["Bidirectional", "Frappe to Wix"]:
						# Sync Frappe price to Wix
						success = mapping.sync_to_wix()
						if success:
							updated_count += 1
					elif mapping.sync_direction == "Wix to Frappe":
						# Sync Wix price to Frappe
						success = mapping.sync_from_wix()
						if success:
							updated_count += 1
				
			except Exception as e:
				frappe.log_error(f"Price sync failed for mapping {mapping_data.name}: {str(e)}", "Wix Integration")
				continue
		
		frappe.logger().info(f"Price sync completed: {updated_count} products updated")
		
	except Exception as e:
		frappe.log_error(f"Product price sync failed: {str(e)}", "Wix Integration")

def cleanup_orphaned_mappings():
	"""Clean up orphaned product mappings"""
	try:
		# Find mappings with deleted items
		orphaned_mappings = frappe.db.sql("""
			SELECT wpm.name 
			FROM `tabWix Product Mapping` wpm
			LEFT JOIN `tabItem` i ON wpm.item_code = i.name
			WHERE i.name IS NULL
		""", as_dict=True)
		
		deleted_count = 0
		for mapping in orphaned_mappings:
			try:
				frappe.delete_doc("Wix Product Mapping", mapping.name)
				deleted_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to delete orphaned mapping {mapping.name}: {str(e)}", "Wix Integration")
				continue
		
		if deleted_count > 0:
			frappe.logger().info(f"Cleaned up {deleted_count} orphaned product mappings")
		
	except Exception as e:
		frappe.log_error(f"Cleanup orphaned mappings failed: {str(e)}", "Wix Integration")

def validate_product_data():
	"""Validate product data consistency between Frappe and Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled:
			return
		
		wix_client = get_wix_client()
		
		# Get all active mappings
		mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={"sync_status": "Synced"},
			fields=["name", "item_code", "wix_product_id"]
		)
		
		validation_errors = []
		
		for mapping_data in mappings:
			try:
				# Get Frappe item data
				item_doc = frappe.get_doc("Item", mapping_data.item_code)
				
				# Get Wix product data
				wix_product = wix_client.get_product(mapping_data.wix_product_id)
				
				if not wix_product:
					validation_errors.append({
						"mapping": mapping_data.name,
						"error": "Product not found in Wix",
						"item_code": mapping_data.item_code
					})
					continue
				
				# Validate name consistency
				wix_name = wix_product.get('name', '')
				if item_doc.item_name != wix_name:
					validation_errors.append({
						"mapping": mapping_data.name,
						"error": f"Name mismatch: Frappe='{item_doc.item_name}', Wix='{wix_name}'",
						"item_code": mapping_data.item_code
					})
				
				# Validate SKU consistency
				wix_sku = wix_product.get('sku', '')
				if item_doc.item_code != wix_sku:
					validation_errors.append({
						"mapping": mapping_data.name,
						"error": f"SKU mismatch: Frappe='{item_doc.item_code}', Wix='{wix_sku}'",
						"item_code": mapping_data.item_code
					})
				
			except Exception as e:
				validation_errors.append({
					"mapping": mapping_data.name,
					"error": f"Validation failed: {str(e)}",
					"item_code": mapping_data.item_code
				})
				continue
		
		if validation_errors:
			frappe.logger().warning(f"Product validation found {len(validation_errors)} errors")
			
			# Create error log
			error_log = frappe.get_doc({
				"doctype": "Error Log",
				"method": "wix_integration.tasks.sync_products.validate_product_data",
				"error": f"Product validation errors: {validation_errors}"
			})
			error_log.insert()
		else:
			frappe.logger().info("Product validation completed successfully - no errors found")
		
	except Exception as e:
		frappe.log_error(f"Product validation failed: {str(e)}", "Wix Integration")