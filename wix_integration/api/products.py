import frappe
from frappe.utils import now
from wix_integration.utils.wix_client import get_wix_client

@frappe.whitelist()
def sync_item_to_wix(doc, method=None):
	"""Sync Frappe item to Wix after creation/update"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return
		
		# Skip if this is a Wix-created item (to avoid loops)
		if hasattr(doc, '_from_wix_sync'):
			return
		
		wix_client = get_wix_client()
		result = wix_client.sync_product_from_frappe(doc.item_code)
		
		if result:
			frappe.logger().info(f"Item {doc.item_code} synced to Wix successfully")
		else:
			frappe.logger().error(f"Failed to sync item {doc.item_code} to Wix")
			
	except Exception as e:
		frappe.log_error(f"Item sync to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def update_item_in_wix(doc, method=None):
	"""Update Frappe item in Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_products:
			return
		
		# Skip if this is a Wix-updated item (to avoid loops)
		if hasattr(doc, '_from_wix_sync'):
			return
		
		# Check if mapping exists
		mapping = frappe.db.get_value("Wix Product Mapping", {"item_code": doc.item_code}, "name")
		if mapping:
			mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
			mapping_doc.sync_to_wix()
			
	except Exception as e:
		frappe.log_error(f"Item update to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def validate_item_sync(doc, method=None):
	"""Validate item before sync"""
	# Add any validation logic here
	pass

@frappe.whitelist()
def update_inventory_to_wix(doc, method=None):
	"""Update inventory in Wix when stock entry is submitted"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_inventory:
			return
		
		wix_client = get_wix_client()
		
		# Process each item in the stock entry
		for item in doc.items:
			# Check if this item has Wix mapping
			mapping = frappe.db.get_value(
				"Wix Product Mapping", 
				{"item_code": item.item_code}, 
				["wix_product_id", "wix_variant_id"]
			)
			
			if mapping:
				wix_product_id, wix_variant_id = mapping
				
				# Get current stock
				current_stock = frappe.db.get_value(
					"Bin",
					{"item_code": item.item_code, "warehouse": item.s_warehouse or item.t_warehouse},
					"actual_qty"
				) or 0
				
				# Update inventory in Wix
				result = wix_client.update_inventory(wix_product_id, wix_variant_id, current_stock)
				
				if result:
					frappe.logger().info(f"Inventory updated in Wix for {item.item_code}: {current_stock}")
				else:
					frappe.logger().error(f"Failed to update inventory in Wix for {item.item_code}")
					
	except Exception as e:
		frappe.log_error(f"Inventory update to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def sync_product_from_wix(wix_product_id):
	"""Sync a single product from Wix to Frappe"""
	try:
		wix_client = get_wix_client()
		wix_product = wix_client.get_product(wix_product_id)
		
		if not wix_product:
			return {"success": False, "message": "Product not found in Wix"}
		
		# Check if mapping exists
		mapping = frappe.db.get_value("Wix Product Mapping", {"wix_product_id": wix_product_id}, "name")
		
		if mapping:
			mapping_doc = frappe.get_doc("Wix Product Mapping", mapping)
			success = mapping_doc.sync_from_wix()
			return {"success": success, "item_code": mapping_doc.item_code}
		else:
			# Create new item and mapping
			return create_item_from_wix_product(wix_product)
			
	except Exception as e:
		frappe.log_error(f"Product sync from Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_all_products_from_wix():
	"""Sync all products from Wix to Frappe"""
	try:
		wix_client = get_wix_client()
		offset = 0
		limit = 50
		total_synced = 0
		
		while True:
			response = wix_client.get_products(limit=limit, offset=offset)
			
			if not response or not response.get('products'):
				break
			
			products = response['products']
			
			for product in products:
				try:
					result = sync_product_from_wix(product['id'])
					if result.get('success'):
						total_synced += 1
				except Exception as e:
					frappe.log_error(f"Failed to sync product {product.get('id')}: {str(e)}", "Wix Integration")
					continue
			
			# Check if we have more products
			if len(products) < limit:
				break
			
			offset += limit
		
		return {"success": True, "total_synced": total_synced}
		
	except Exception as e:
		frappe.log_error(f"Bulk product sync from Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def create_item_from_wix_product(wix_product):
	"""Create Frappe item from Wix product"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.auto_create_items:
			return {"success": False, "message": "Auto create items is disabled"}
		
		product_data = wix_product.get('product', wix_product)
		
		# Generate item code
		item_code = product_data.get('sku') or f"WIX-{product_data.get('id', '')}"
		
		# Check if item already exists
		if frappe.db.exists("Item", item_code):
			return {"success": False, "message": f"Item {item_code} already exists"}
		
		# Create item
		item_doc = frappe.get_doc({
			"doctype": "Item",
			"item_code": item_code,
			"item_name": product_data.get('name', item_code),
			"description": product_data.get('description', ''),
			"item_group": "Products",
			"stock_uom": "Nos",
			"is_sales_item": 1,
			"is_purchase_item": 0,
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"_from_wix_sync": True  # Flag to prevent sync loop
		})
		item_doc.insert()
		
		# Create item price if available
		price_data = product_data.get('priceData', {})
		if price_data.get('price') and settings.default_price_list:
			frappe.get_doc({
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": settings.default_price_list,
				"price_list_rate": float(price_data['price'])
			}).insert()
		
		# Create product mapping
		from wix_integration.doctype.wix_product_mapping.wix_product_mapping import create_product_mapping
		mapping = create_product_mapping(item_code, product_data['id'])
		
		# Update mapping with Wix data
		mapping.wix_product_name = product_data.get('name')
		mapping.wix_sku = product_data.get('sku')
		mapping.wix_price = float(price_data.get('price', 0)) if price_data.get('price') else 0
		mapping.wix_inventory_tracking = product_data.get('inventory', {}).get('trackQuantity', False)
		mapping.sync_status = "Synced"
		mapping.last_sync_time = now()
		mapping.save()
		
		return {"success": True, "item_code": item_code, "mapping": mapping.name}
		
	except Exception as e:
		frappe.log_error(f"Item creation from Wix product failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def get_product_sync_status():
	"""Get status of product synchronization"""
	try:
		total_mappings = frappe.db.count("Wix Product Mapping")
		synced_mappings = frappe.db.count("Wix Product Mapping", {"sync_status": "Synced"})
		error_mappings = frappe.db.count("Wix Product Mapping", {"sync_status": "Error"})
		pending_mappings = frappe.db.count("Wix Product Mapping", {"sync_status": "Pending"})
		
		return {
			"total": total_mappings,
			"synced": synced_mappings,
			"errors": error_mappings,
			"pending": pending_mappings,
			"sync_rate": (synced_mappings / total_mappings * 100) if total_mappings > 0 else 0
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get product sync status: {str(e)}", "Wix Integration")
		return {"error": str(e)}

@frappe.whitelist()
def retry_failed_product_syncs():
	"""Retry failed product synchronizations"""
	try:
		failed_mappings = frappe.get_all(
			"Wix Product Mapping",
			filters={"sync_status": "Error"},
			fields=["name", "item_code", "sync_direction"]
		)
		
		retry_count = 0
		success_count = 0
		
		for mapping_data in failed_mappings:
			try:
				mapping = frappe.get_doc("Wix Product Mapping", mapping_data.name)
				
				if mapping_data.sync_direction in ["Bidirectional", "Frappe to Wix"]:
					success = mapping.sync_to_wix()
				else:
					success = mapping.sync_from_wix()
				
				if success:
					success_count += 1
				retry_count += 1
				
			except Exception as e:
				frappe.log_error(f"Retry sync failed for mapping {mapping_data.name}: {str(e)}", "Wix Integration")
				continue
		
		return {
			"success": True,
			"retried": retry_count,
			"succeeded": success_count,
			"failed": retry_count - success_count
		}
		
	except Exception as e:
		frappe.log_error(f"Retry failed syncs failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}