import frappe
from frappe.model.document import Document
from frappe.utils import now, flt

class WixProductMapping(Document):
	def validate(self):
		"""Validate product mapping"""
		self.calculate_differences()
		self.update_sync_status()
	
	def calculate_differences(self):
		"""Calculate price and stock differences between Frappe and Wix"""
		if self.frappe_price and self.wix_price:
			self.price_difference = flt(self.frappe_price) - flt(self.wix_price)
		
		if self.frappe_stock_qty and hasattr(self, 'wix_stock_qty'):
			self.stock_difference = flt(self.frappe_stock_qty) - flt(getattr(self, 'wix_stock_qty', 0))
	
	def update_sync_status(self):
		"""Update sync status based on differences"""
		if abs(flt(self.price_difference)) > 0.01 or abs(flt(self.stock_difference)) > 0:
			if self.sync_status == "Synced":
				self.sync_status = "Conflict"
	
	def sync_to_wix(self):
		"""Sync this product to Wix"""
		try:
			from wix_integration.utils.wix_client import WixClient
			
			wix_client = WixClient()
			item_doc = frappe.get_doc("Item", self.item_code)
			
			# Get current price from price list
			price_list_rate = frappe.db.get_value(
				"Item Price",
				{"item_code": self.item_code, "price_list": frappe.db.get_single_value("Wix Integration Settings", "default_price_list")},
				"price_list_rate"
			)
			
			# Get current stock
			stock_qty = frappe.db.get_value(
				"Bin",
				{"item_code": self.item_code, "warehouse": frappe.db.get_single_value("Wix Integration Settings", "default_warehouse")},
				"actual_qty"
			) or 0
			
			# Update product in Wix
			product_data = {
				"name": item_doc.item_name,
				"description": item_doc.description,
				"sku": item_doc.item_code,
				"price": price_list_rate or 0,
				"inventory": {
					"trackQuantity": True,
					"quantity": int(stock_qty)
				}
			}
			
			success = wix_client.update_product(self.wix_product_id, product_data)
			
			if success:
				self.sync_status = "Synced"
				self.last_sync_time = now()
				self.frappe_price = price_list_rate
				self.frappe_stock_qty = stock_qty
				self.error_log = ""
				self.save()
				return True
			else:
				self.sync_status = "Error"
				self.error_log = "Failed to sync to Wix"
				self.last_error_time = now()
				self.save()
				return False
				
		except Exception as e:
			self.sync_status = "Error"
			self.error_log = str(e)
			self.last_error_time = now()
			self.save()
			frappe.log_error(f"Product sync to Wix failed for {self.item_code}: {str(e)}", "Wix Integration")
			return False
	
	def sync_from_wix(self):
		"""Sync this product from Wix"""
		try:
			from wix_integration.utils.wix_client import WixClient
			
			wix_client = WixClient()
			wix_product = wix_client.get_product(self.wix_product_id)
			
			if not wix_product:
				self.sync_status = "Error"
				self.error_log = "Product not found in Wix"
				self.last_error_time = now()
				self.save()
				return False
			
			# Update Frappe item
			item_doc = frappe.get_doc("Item", self.item_code)
			item_doc.item_name = wix_product.get("name", item_doc.item_name)
			item_doc.description = wix_product.get("description", item_doc.description)
			item_doc.save()
			
			# Update price if price list is configured
			default_price_list = frappe.db.get_single_value("Wix Integration Settings", "default_price_list")
			if default_price_list and wix_product.get("price"):
				if frappe.db.exists("Item Price", {"item_code": self.item_code, "price_list": default_price_list}):
					price_doc = frappe.get_doc("Item Price", {"item_code": self.item_code, "price_list": default_price_list})
					price_doc.price_list_rate = wix_product["price"]
					price_doc.save()
				else:
					frappe.get_doc({
						"doctype": "Item Price",
						"item_code": self.item_code,
						"price_list": default_price_list,
						"price_list_rate": wix_product["price"]
					}).insert()
			
			# Update Wix data in mapping
			self.wix_product_name = wix_product.get("name")
			self.wix_sku = wix_product.get("sku")
			self.wix_price = wix_product.get("price")
			self.wix_inventory_tracking = wix_product.get("inventory", {}).get("trackQuantity", False)
			
			self.sync_status = "Synced"
			self.last_sync_time = now()
			self.error_log = ""
			self.save()
			return True
			
		except Exception as e:
			self.sync_status = "Error"
			self.error_log = str(e)
			self.last_error_time = now()
			self.save()
			frappe.log_error(f"Product sync from Wix failed for {self.item_code}: {str(e)}", "Wix Integration")
			return False

@frappe.whitelist()
def create_product_mapping(item_code, wix_product_id, wix_variant_id=None):
	"""Create a new product mapping"""
	if frappe.db.exists("Wix Product Mapping", {"item_code": item_code, "wix_product_id": wix_product_id}):
		return frappe.get_doc("Wix Product Mapping", {"item_code": item_code, "wix_product_id": wix_product_id})
	
	mapping = frappe.get_doc({
		"doctype": "Wix Product Mapping",
		"item_code": item_code,
		"wix_product_id": wix_product_id,
		"wix_variant_id": wix_variant_id,
		"is_variant": bool(wix_variant_id)
	})
	mapping.insert()
	return mapping