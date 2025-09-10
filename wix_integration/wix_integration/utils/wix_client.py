import frappe
import requests
import json
from datetime import datetime, timedelta
import time

class WixClient:
	"""Wix API Client for handling all Wix API interactions"""
	
	def __init__(self):
		self.settings = frappe.get_single("Wix Integration Settings")
		self.base_url = "https://www.wixapis.com"
		self.access_token = None
		self.instance_id = None
		
		if self.settings and self.settings.enabled:
			self.access_token = self.settings.get_password("wix_access_token")
			self.instance_id = self.settings.wix_instance_id
	
	def get_headers(self):
		"""Get headers for API requests"""
		if not self.access_token:
			self.refresh_token()
		
		return {
			"Authorization": f"Bearer {self.access_token}",
			"Content-Type": "application/json",
			"wix-instance-id": self.instance_id
		}
	
	def refresh_token(self):
		"""Refresh access token if needed"""
		if self.settings:
			success = self.settings.refresh_access_token()
			if success:
				self.access_token = self.settings.get_password("wix_access_token")
			return success
		return False
	
	def make_request(self, method, endpoint, data=None, params=None, retry=True):
		"""Make API request with automatic retry on auth failure"""
		try:
			url = f"{self.base_url}{endpoint}"
			headers = self.get_headers()
			
			if method.upper() == "GET":
				response = requests.get(url, headers=headers, params=params, timeout=30)
			elif method.upper() == "POST":
				response = requests.post(url, headers=headers, json=data, params=params, timeout=30)
			elif method.upper() == "PUT":
				response = requests.put(url, headers=headers, json=data, params=params, timeout=30)
			elif method.upper() == "PATCH":
				response = requests.patch(url, headers=headers, json=data, params=params, timeout=30)
			elif method.upper() == "DELETE":
				response = requests.delete(url, headers=headers, params=params, timeout=30)
			else:
				raise ValueError(f"Unsupported HTTP method: {method}")
			
			# Handle rate limiting
			if response.status_code == 429:
				retry_after = int(response.headers.get('Retry-After', 60))
				frappe.log_error(f"Rate limited, waiting {retry_after} seconds", "Wix Integration")
				time.sleep(retry_after)
				return self.make_request(method, endpoint, data, params, retry=False)
			
			# Handle auth errors
			if response.status_code == 401 and retry:
				if self.refresh_token():
					return self.make_request(method, endpoint, data, params, retry=False)
			
			if response.status_code >= 400:
				frappe.log_error(f"Wix API Error {response.status_code}: {response.text}", "Wix Integration")
				return None
			
			return response.json() if response.text else {}
			
		except requests.exceptions.RequestException as e:
			frappe.log_error(f"Wix API Request failed: {str(e)}", "Wix Integration")
			return None
		except Exception as e:
			frappe.log_error(f"Wix API Error: {str(e)}", "Wix Integration")
			return None
	
	# Product API methods
	def get_products(self, limit=100, offset=0):
		"""Get products from Wix"""
		params = {
			"query": {
				"limit": limit,
				"offset": offset
			}
		}
		return self.make_request("POST", "/stores/v1/products/query", data=params)
	
	def get_product(self, product_id):
		"""Get single product from Wix"""
		return self.make_request("GET", f"/stores/v1/products/{product_id}")
	
	def create_product(self, product_data):
		"""Create product in Wix"""
		return self.make_request("POST", "/stores/v1/products", data={"product": product_data})
	
	def update_product(self, product_id, product_data):
		"""Update product in Wix"""
		return self.make_request("PATCH", f"/stores/v1/products/{product_id}", data={"product": product_data})
	
	def delete_product(self, product_id):
		"""Delete product in Wix"""
		return self.make_request("DELETE", f"/stores/v1/products/{product_id}")
	
	def update_inventory(self, product_id, variant_id=None, quantity=0):
		"""Update inventory for a product/variant"""
		inventory_data = {
			"inventoryItem": {
				"trackQuantity": True,
				"quantity": int(quantity)
			}
		}
		
		if variant_id:
			endpoint = f"/stores/v1/products/{product_id}/variants/{variant_id}/inventory"
		else:
			endpoint = f"/stores/v1/products/{product_id}/inventory"
		
		return self.make_request("PATCH", endpoint, data=inventory_data)
	
	# Order API methods
	def get_orders(self, limit=100, offset=0, status=None):
		"""Get orders from Wix"""
		query = {
			"limit": limit,
			"offset": offset
		}
		
		if status:
			query["filter"] = {"status": status}
		
		params = {"query": query}
		return self.make_request("POST", "/stores/v1/orders/query", data=params)
	
	def get_order(self, order_id):
		"""Get single order from Wix"""
		return self.make_request("GET", f"/stores/v1/orders/{order_id}")
	
	def update_order_fulfillment(self, order_id, fulfillment_data):
		"""Update order fulfillment status"""
		return self.make_request("POST", f"/stores/v1/orders/{order_id}/fulfillments", data=fulfillment_data)
	
	def cancel_order(self, order_id):
		"""Cancel order in Wix"""
		return self.make_request("POST", f"/stores/v1/orders/{order_id}/cancel")
	
	# Customer API methods
	def get_customers(self, limit=100, offset=0):
		"""Get customers from Wix"""
		params = {
			"query": {
				"limit": limit,
				"offset": offset
			}
		}
		return self.make_request("POST", "/stores/v1/customers/query", data=params)
	
	def get_customer(self, customer_id):
		"""Get single customer from Wix"""
		return self.make_request("GET", f"/stores/v1/customers/{customer_id}")
	
	def create_customer(self, customer_data):
		"""Create customer in Wix"""
		return self.make_request("POST", "/stores/v1/customers", data={"customer": customer_data})
	
	def update_customer(self, customer_id, customer_data):
		"""Update customer in Wix"""
		return self.make_request("PATCH", f"/stores/v1/customers/{customer_id}", data={"customer": customer_data})
	
	# Collection API methods
	def get_collections(self):
		"""Get product collections from Wix"""
		return self.make_request("GET", "/stores/v1/collections")
	
	def get_collection_products(self, collection_id):
		"""Get products in a collection"""
		return self.make_request("GET", f"/stores/v1/collections/{collection_id}/products")
	
	# Webhook validation
	def validate_webhook_signature(self, payload, signature):
		"""Validate webhook signature"""
		import hmac
		import hashlib
		
		if not self.settings or not self.settings.wix_webhook_secret:
			return False
		
		webhook_secret = self.settings.get_password("wix_webhook_secret")
		expected_signature = hmac.new(
			webhook_secret.encode(),
			payload.encode() if isinstance(payload, str) else payload,
			hashlib.sha256
		).hexdigest()
		
		return hmac.compare_digest(f"sha256={expected_signature}", signature)
	
	# Bulk operations
	def bulk_update_inventory(self, inventory_updates):
		"""Bulk update inventory for multiple products"""
		success_count = 0
		error_count = 0
		
		for update in inventory_updates:
			try:
				result = self.update_inventory(
					update.get('product_id'),
					update.get('variant_id'),
					update.get('quantity', 0)
				)
				
				if result:
					success_count += 1
				else:
					error_count += 1
					
			except Exception as e:
				error_count += 1
				frappe.log_error(f"Bulk inventory update failed for product {update.get('product_id')}: {str(e)}", "Wix Integration")
		
		return {
			"success_count": success_count,
			"error_count": error_count,
			"total": len(inventory_updates)
		}
	
	def sync_product_from_frappe(self, item_code):
		"""Sync a Frappe item to Wix"""
		try:
			item_doc = frappe.get_doc("Item", item_code)
			
			# Get price from default price list
			price = 0
			if self.settings.default_price_list:
				price_doc = frappe.db.get_value(
					"Item Price",
					{"item_code": item_code, "price_list": self.settings.default_price_list},
					"price_list_rate"
				)
				price = price_doc or 0
			
			# Get stock quantity
			stock_qty = 0
			if self.settings.default_warehouse:
				stock_qty = frappe.db.get_value(
					"Bin",
					{"item_code": item_code, "warehouse": self.settings.default_warehouse},
					"actual_qty"
				) or 0
			
			# Prepare product data for Wix
			product_data = {
				"name": item_doc.item_name,
				"description": item_doc.description or "",
				"sku": item_doc.item_code,
				"visible": True,
				"priceData": {
					"price": str(price),
					"currency": "USD"  # Should be configurable
				},
				"manageVariants": False,
				"productType": "physical",
				"inventory": {
					"trackQuantity": True,
					"quantity": int(stock_qty)
				}
			}
			
			# Check if product already exists in Wix
			mapping = frappe.db.get_value("Wix Product Mapping", {"item_code": item_code}, "wix_product_id")
			
			if mapping:
				# Update existing product
				result = self.update_product(mapping, product_data)
			else:
				# Create new product
				result = self.create_product(product_data)
				
				if result and result.get('product', {}).get('id'):
					# Create mapping
					from wix_integration.doctype.wix_product_mapping.wix_product_mapping import create_product_mapping
					create_product_mapping(item_code, result['product']['id'])
			
			return result
			
		except Exception as e:
			frappe.log_error(f"Product sync to Wix failed for {item_code}: {str(e)}", "Wix Integration")
			return None

# Singleton instance
wix_client = None

def get_wix_client():
	"""Get singleton Wix client instance"""
	global wix_client
	if wix_client is None:
		wix_client = WixClient()
	return wix_client