import frappe
from frappe.model.document import Document
from frappe.utils import now
import requests
import json

class WixIntegrationSettings(Document):
	def validate(self):
		"""Validate Wix credentials and connection"""
		if self.enabled and self.wix_app_id and self.wix_app_secret:
			self.test_wix_connection()
	
	def test_wix_connection(self):
		"""Test connection to Wix API"""
		try:
			if self.wix_access_token:
				headers = {
					'Authorization': f'Bearer {self.get_password("wix_access_token")}',
					'Content-Type': 'application/json'
				}
				
				# Test with Wix Stores API
				response = requests.get(
					f'https://www.wixapis.com/stores/v1/products/query',
					headers=headers,
					timeout=10
				)
				
				if response.status_code == 200:
					self.sync_status = "Success"
					self.error_log = ""
				else:
					self.sync_status = "Error"
					self.error_log = f"Wix API Error: {response.status_code} - {response.text}"
			else:
				self.sync_status = "Error"
				self.error_log = "Access token not found. Please authenticate with Wix."
				
		except Exception as e:
			self.sync_status = "Error"
			self.error_log = f"Connection test failed: {str(e)}"
			frappe.log_error(f"Wix connection test failed: {str(e)}", "Wix Integration")
	
	def refresh_access_token(self):
		"""Refresh Wix access token using refresh token"""
		try:
			if not self.wix_refresh_token:
				frappe.throw("Refresh token not found")
			
			data = {
				'grant_type': 'refresh_token',
				'client_id': self.wix_app_id,
				'client_secret': self.get_password("wix_app_secret"),
				'refresh_token': self.get_password("wix_refresh_token")
			}
			
			response = requests.post(
				'https://www.wixapis.com/oauth/access',
				data=data,
				timeout=10
			)
			
			if response.status_code == 200:
				token_data = response.json()
				self.wix_access_token = token_data.get('access_token')
				if token_data.get('refresh_token'):
					self.wix_refresh_token = token_data.get('refresh_token')
				self.save()
				return True
			else:
				frappe.log_error(f"Token refresh failed: {response.text}", "Wix Integration")
				return False
				
		except Exception as e:
			frappe.log_error(f"Token refresh error: {str(e)}", "Wix Integration")
			return False
	
	@frappe.whitelist()
	def sync_all_data(self):
		"""Trigger full synchronization of all data"""
		if not self.enabled:
			frappe.throw("Wix Integration is disabled")
		
		try:
			self.sync_status = "Syncing"
			self.save()
			
			# Import here to avoid circular imports
			from wix_integration.tasks.sync_products import sync_all_products
			from wix_integration.tasks.sync_customers import sync_all_customers
			from wix_integration.tasks.sync_orders import sync_all_orders
			from wix_integration.tasks.sync_inventory import sync_all_inventory
			
			# Run sync tasks
			if self.sync_products:
				sync_all_products()
			
			if self.sync_customers:
				sync_all_customers()
			
			if self.sync_orders:
				sync_all_orders()
			
			if self.sync_inventory:
				sync_all_inventory()
			
			self.last_sync_time = now()
			self.sync_status = "Success"
			self.error_log = ""
			self.save()
			
			frappe.msgprint("Synchronization completed successfully")
			
		except Exception as e:
			self.sync_status = "Error"
			self.error_log = str(e)
			self.save()
			frappe.log_error(f"Full sync failed: {str(e)}", "Wix Integration")
			frappe.throw(f"Synchronization failed: {str(e)}")

@frappe.whitelist()
def get_wix_settings():
	"""Get Wix integration settings"""
	if frappe.db.exists("Wix Integration Settings", "Wix Integration Settings"):
		return frappe.get_doc("Wix Integration Settings", "Wix Integration Settings")
	else:
		# Create default settings
		doc = frappe.get_doc({
			"doctype": "Wix Integration Settings",
			"title": "Wix Integration Settings"
		})
		doc.insert()
		return doc