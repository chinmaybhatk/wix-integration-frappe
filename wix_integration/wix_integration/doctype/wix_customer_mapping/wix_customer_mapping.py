import frappe
from frappe.model.document import Document
from frappe.utils import now

class WixCustomerMapping(Document):
	def validate(self):
		"""Validate customer mapping"""
		self.update_customer_info()
	
	def update_customer_info(self):
		"""Update customer information from linked customer"""
		if self.customer:
			customer_doc = frappe.get_doc("Customer", self.customer)
			self.frappe_customer_name = customer_doc.customer_name
			
			# Get contact details
			contact = frappe.db.get_value(
				"Dynamic Link",
				{"link_doctype": "Customer", "link_name": self.customer, "parenttype": "Contact"},
				"parent"
			)
			
			if contact:
				contact_doc = frappe.get_doc("Contact", contact)
				self.frappe_email_id = contact_doc.email_id
				self.frappe_mobile_no = contact_doc.mobile_no
			
			# Count total orders
			self.total_orders = frappe.db.count("Sales Order", {"customer": self.customer})
	
	def sync_to_wix(self):
		"""Sync this customer to Wix"""
		try:
			from wix_integration.utils.wix_client import WixClient
			
			wix_client = WixClient()
			customer_doc = frappe.get_doc("Customer", self.customer)
			
			# Get contact details
			contact = frappe.db.get_value(
				"Dynamic Link",
				{"link_doctype": "Customer", "link_name": self.customer, "parenttype": "Contact"},
				"parent"
			)
			
			contact_doc = None
			if contact:
				contact_doc = frappe.get_doc("Contact", contact)
			
			# Prepare customer data
			customer_data = {
				"firstName": customer_doc.customer_name.split()[0] if customer_doc.customer_name else "",
				"lastName": " ".join(customer_doc.customer_name.split()[1:]) if len(customer_doc.customer_name.split()) > 1 else "",
				"emails": [contact_doc.email_id] if contact_doc and contact_doc.email_id else [],
				"phones": [contact_doc.mobile_no] if contact_doc and contact_doc.mobile_no else []
			}
			
			success = wix_client.update_customer(self.wix_customer_id, customer_data)
			
			if success:
				self.sync_status = "Synced"
				self.last_sync_time = now()
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
			frappe.log_error(f"Customer sync to Wix failed for {self.customer}: {str(e)}", "Wix Integration")
			return False
	
	def sync_from_wix(self):
		"""Sync this customer from Wix"""
		try:
			from wix_integration.utils.wix_client import WixClient
			
			wix_client = WixClient()
			wix_customer = wix_client.get_customer(self.wix_customer_id)
			
			if not wix_customer:
				self.sync_status = "Error"
				self.error_log = "Customer not found in Wix"
				self.last_error_time = now()
				self.save()
				return False
			
			# Update Frappe customer
			customer_doc = frappe.get_doc("Customer", self.customer)
			
			# Update customer name if needed
			wix_name = f"{wix_customer.get('firstName', '')} {wix_customer.get('lastName', '')}".strip()
			if wix_name and wix_name != customer_doc.customer_name:
				customer_doc.customer_name = wix_name
				customer_doc.save()
			
			# Update contact information
			contact = frappe.db.get_value(
				"Dynamic Link",
				{"link_doctype": "Customer", "link_name": self.customer, "parenttype": "Contact"},
				"parent"
			)
			
			if contact:
				contact_doc = frappe.get_doc("Contact", contact)
			else:
				# Create new contact
				contact_doc = frappe.get_doc({
					"doctype": "Contact",
					"first_name": wix_customer.get('firstName', ''),
					"last_name": wix_customer.get('lastName', ''),
					"links": [{
						"link_doctype": "Customer",
						"link_name": self.customer
					}]
				})
			
			# Update email and phone
			if wix_customer.get('emails') and len(wix_customer['emails']) > 0:
				contact_doc.email_id = wix_customer['emails'][0]
				self.email = wix_customer['emails'][0]
			
			if wix_customer.get('phones') and len(wix_customer['phones']) > 0:
				contact_doc.mobile_no = wix_customer['phones'][0]
			
			contact_doc.save()
			
			# Update Wix data in mapping
			self.wix_first_name = wix_customer.get('firstName')
			self.wix_last_name = wix_customer.get('lastName')
			self.wix_email = wix_customer.get('emails', [None])[0]
			self.wix_phone = wix_customer.get('phones', [None])[0]
			
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
			frappe.log_error(f"Customer sync from Wix failed for {self.customer}: {str(e)}", "Wix Integration")
			return False

@frappe.whitelist()
def create_customer_mapping(customer, wix_customer_id, email=None):
	"""Create a new customer mapping"""
	if frappe.db.exists("Wix Customer Mapping", {"customer": customer, "wix_customer_id": wix_customer_id}):
		return frappe.get_doc("Wix Customer Mapping", {"customer": customer, "wix_customer_id": wix_customer_id})
	
	mapping = frappe.get_doc({
		"doctype": "Wix Customer Mapping",
		"customer": customer,
		"wix_customer_id": wix_customer_id,
		"email": email
	})
	mapping.insert()
	return mapping

@frappe.whitelist()
def get_or_create_customer_from_wix(wix_customer_data):
	"""Get existing customer or create new one from Wix data"""
	email = None
	if wix_customer_data.get('emails') and len(wix_customer_data['emails']) > 0:
		email = wix_customer_data['emails'][0]
	
	# Try to find existing customer by email
	existing_customer = None
	if email:
		contact = frappe.db.get_value("Contact", {"email_id": email}, "name")
		if contact:
			customer_link = frappe.db.get_value(
				"Dynamic Link",
				{"parent": contact, "link_doctype": "Customer"},
				"link_name"
			)
			if customer_link:
				existing_customer = customer_link
	
	if existing_customer:
		return existing_customer
	
	# Create new customer
	customer_name = f"{wix_customer_data.get('firstName', '')} {wix_customer_data.get('lastName', '')}".strip()
	if not customer_name:
		customer_name = email or f"Wix Customer {wix_customer_data.get('id', '')}"
	
	settings = frappe.get_single("Wix Integration Settings")
	
	customer_doc = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": customer_name,
		"customer_group": settings.default_customer_group or "Individual",
		"territory": settings.default_territory or "All Territories"
	})
	customer_doc.insert()
	
	# Create contact
	if email or wix_customer_data.get('phones'):
		contact_doc = frappe.get_doc({
			"doctype": "Contact",
			"first_name": wix_customer_data.get('firstName', ''),
			"last_name": wix_customer_data.get('lastName', ''),
			"email_id": email,
			"mobile_no": wix_customer_data.get('phones', [None])[0],
			"links": [{
				"link_doctype": "Customer",
				"link_name": customer_doc.name
			}]
		})
		contact_doc.insert()
	
	return customer_doc.name