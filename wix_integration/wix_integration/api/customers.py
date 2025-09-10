import frappe
from frappe.utils import now
from wix_integration.utils.wix_client import get_wix_client

@frappe.whitelist()
def sync_customer_to_wix(doc, method=None):
	"""Sync Frappe customer to Wix after creation"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_customers:
			return
		
		# Skip if this is a Wix-created customer (to avoid loops)
		if hasattr(doc, '_from_wix_sync'):
			return
		
		# Check if customer already has Wix mapping
		mapping = frappe.db.get_value("Wix Customer Mapping", {"customer": doc.name}, "name")
		
		if not mapping:
			# Create customer in Wix
			create_customer_in_wix(doc.name)
			
	except Exception as e:
		frappe.log_error(f"Customer sync to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def update_customer_in_wix(doc, method=None):
	"""Update Frappe customer in Wix"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.enabled or not settings.sync_customers:
			return
		
		# Skip if this is a Wix-updated customer (to avoid loops)
		if hasattr(doc, '_from_wix_sync'):
			return
		
		# Check if mapping exists
		mapping = frappe.db.get_value("Wix Customer Mapping", {"customer": doc.name}, "name")
		if mapping:
			mapping_doc = frappe.get_doc("Wix Customer Mapping", mapping)
			mapping_doc.sync_to_wix()
			
	except Exception as e:
		frappe.log_error(f"Customer update to Wix failed: {str(e)}", "Wix Integration")

@frappe.whitelist()
def create_customer_in_wix(customer_name):
	"""Create a Frappe customer in Wix"""
	try:
		wix_client = get_wix_client()
		customer_doc = frappe.get_doc("Customer", customer_name)
		
		# Get contact details
		contact = frappe.db.get_value(
			"Dynamic Link",
			{"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Contact"},
			"parent"
		)
		
		contact_doc = None
		if contact:
			contact_doc = frappe.get_doc("Contact", contact)
		
		# Prepare customer data for Wix
		customer_data = {
			"firstName": customer_doc.customer_name.split()[0] if customer_doc.customer_name else "",
			"lastName": " ".join(customer_doc.customer_name.split()[1:]) if len(customer_doc.customer_name.split()) > 1 else "",
		}
		
		# Add contact information if available
		if contact_doc:
			if contact_doc.email_id:
				customer_data["emails"] = [contact_doc.email_id]
			if contact_doc.mobile_no:
				customer_data["phones"] = [contact_doc.mobile_no]
		
		# Create customer in Wix
		result = wix_client.create_customer(customer_data)
		
		if result and result.get('customer', {}).get('id'):
			wix_customer_id = result['customer']['id']
			
			# Create customer mapping
			from wix_integration.doctype.wix_customer_mapping.wix_customer_mapping import create_customer_mapping
			
			email = contact_doc.email_id if contact_doc else None
			mapping = create_customer_mapping(customer_name, wix_customer_id, email)
			
			# Update mapping with Wix data
			wix_customer = result['customer']
			mapping.wix_first_name = wix_customer.get('firstName')
			mapping.wix_last_name = wix_customer.get('lastName')
			mapping.wix_email = wix_customer.get('emails', [None])[0]
			mapping.wix_phone = wix_customer.get('phones', [None])[0]
			mapping.sync_status = "Synced"
			mapping.last_sync_time = now()
			mapping.save()
			
			return {"success": True, "wix_customer_id": wix_customer_id, "mapping": mapping.name}
		else:
			return {"success": False, "message": "Failed to create customer in Wix"}
			
	except Exception as e:
		frappe.log_error(f"Customer creation in Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_customer_from_wix(wix_customer_id):
	"""Sync a single customer from Wix to Frappe"""
	try:
		wix_client = get_wix_client()
		wix_customer = wix_client.get_customer(wix_customer_id)
		
		if not wix_customer:
			return {"success": False, "message": "Customer not found in Wix"}
		
		# Check if mapping exists
		mapping = frappe.db.get_value("Wix Customer Mapping", {"wix_customer_id": wix_customer_id}, "name")
		
		if mapping:
			mapping_doc = frappe.get_doc("Wix Customer Mapping", mapping)
			success = mapping_doc.sync_from_wix()
			return {"success": success, "customer": mapping_doc.customer}
		else:
			# Create new customer and mapping
			return create_customer_from_wix_data(wix_customer)
			
	except Exception as e:
		frappe.log_error(f"Customer sync from Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_all_customers_from_wix():
	"""Sync all customers from Wix to Frappe"""
	try:
		wix_client = get_wix_client()
		offset = 0
		limit = 50
		total_synced = 0
		
		while True:
			response = wix_client.get_customers(limit=limit, offset=offset)
			
			if not response or not response.get('customers'):
				break
			
			customers = response['customers']
			
			for customer in customers:
				try:
					result = sync_customer_from_wix(customer['id'])
					if result.get('success'):
						total_synced += 1
				except Exception as e:
					frappe.log_error(f"Failed to sync customer {customer.get('id')}: {str(e)}", "Wix Integration")
					continue
			
			# Check if we have more customers
			if len(customers) < limit:
				break
			
			offset += limit
		
		return {"success": True, "total_synced": total_synced}
		
	except Exception as e:
		frappe.log_error(f"Bulk customer sync from Wix failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

def create_customer_from_wix_data(wix_customer_data):
	"""Create Frappe customer from Wix customer data"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		if not settings.auto_create_customers:
			return {"success": False, "message": "Auto create customers is disabled"}
		
		customer_data = wix_customer_data.get('customer', wix_customer_data)
		
		# Generate customer name
		first_name = customer_data.get('firstName', '')
		last_name = customer_data.get('lastName', '')
		customer_name = f"{first_name} {last_name}".strip()
		
		if not customer_name:
			# Use email or generate name
			email = customer_data.get('emails', [None])[0]
			customer_name = email or f"Wix Customer {customer_data.get('id', '')}"
		
		# Check if customer already exists
		existing_customer = None
		email = customer_data.get('emails', [None])[0]
		
		if email:
			# Try to find existing customer by email
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
			customer_doc = frappe.get_doc("Customer", existing_customer)
		else:
			# Create new customer
			customer_doc = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_group": settings.default_customer_group or "Individual",
				"territory": settings.default_territory or "All Territories",
				"_from_wix_sync": True  # Flag to prevent sync loop
			})
			customer_doc.insert()
			
			# Create contact if email or phone available
			if email or customer_data.get('phones'):
				contact_doc = frappe.get_doc({
					"doctype": "Contact",
					"first_name": first_name,
					"last_name": last_name,
					"email_id": email,
					"mobile_no": customer_data.get('phones', [None])[0],
					"links": [{
						"link_doctype": "Customer",
						"link_name": customer_doc.name
					}]
				})
				contact_doc.insert()
		
		# Create customer mapping
		from wix_integration.doctype.wix_customer_mapping.wix_customer_mapping import create_customer_mapping
		mapping = create_customer_mapping(customer_doc.name, customer_data['id'], email)
		
		# Update mapping with Wix data
		mapping.wix_first_name = first_name
		mapping.wix_last_name = last_name
		mapping.wix_email = email
		mapping.wix_phone = customer_data.get('phones', [None])[0]
		mapping.sync_status = "Synced"
		mapping.last_sync_time = now()
		mapping.save()
		
		return {"success": True, "customer": customer_doc.name, "mapping": mapping.name}
		
	except Exception as e:
		frappe.log_error(f"Customer creation from Wix data failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def get_customer_sync_status():
	"""Get status of customer synchronization"""
	try:
		total_mappings = frappe.db.count("Wix Customer Mapping")
		synced_mappings = frappe.db.count("Wix Customer Mapping", {"sync_status": "Synced"})
		error_mappings = frappe.db.count("Wix Customer Mapping", {"sync_status": "Error"})
		pending_mappings = frappe.db.count("Wix Customer Mapping", {"sync_status": "Pending"})
		
		# Get recent customers (last 24 hours)
		recent_customers = frappe.db.count("Wix Customer Mapping", {
			"creation": [">=", frappe.utils.add_days(now(), -1)]
		})
		
		return {
			"total": total_mappings,
			"synced": synced_mappings,
			"errors": error_mappings,
			"pending": pending_mappings,
			"recent": recent_customers,
			"sync_rate": (synced_mappings / total_mappings * 100) if total_mappings > 0 else 0
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get customer sync status: {str(e)}", "Wix Integration")
		return {"error": str(e)}

@frappe.whitelist()
def retry_failed_customer_syncs():
	"""Retry failed customer synchronizations"""
	try:
		failed_mappings = frappe.get_all(
			"Wix Customer Mapping",
			filters={"sync_status": "Error"},
			fields=["name", "customer", "sync_direction"]
		)
		
		retry_count = 0
		success_count = 0
		
		for mapping_data in failed_mappings:
			try:
				mapping = frappe.get_doc("Wix Customer Mapping", mapping_data.name)
				
				if mapping_data.sync_direction in ["Bidirectional", "Frappe to Wix"]:
					success = mapping.sync_to_wix()
				else:
					success = mapping.sync_from_wix()
				
				if success:
					success_count += 1
				retry_count += 1
				
			except Exception as e:
				frappe.log_error(f"Retry customer sync failed for mapping {mapping_data.name}: {str(e)}", "Wix Integration")
				continue
		
		return {
			"success": True,
			"retried": retry_count,
			"succeeded": success_count,
			"failed": retry_count - success_count
		}
		
	except Exception as e:
		frappe.log_error(f"Retry failed customer syncs failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def merge_duplicate_customers(primary_customer, duplicate_customers):
	"""Merge duplicate customers and update mappings"""
	try:
		if isinstance(duplicate_customers, str):
			import json
			duplicate_customers = json.loads(duplicate_customers)
		
		primary_doc = frappe.get_doc("Customer", primary_customer)
		
		for duplicate_customer in duplicate_customers:
			try:
				# Get all sales orders from duplicate customer
				sales_orders = frappe.get_all("Sales Order", {"customer": duplicate_customer})
				
				# Update sales orders to primary customer
				for so in sales_orders:
					frappe.db.set_value("Sales Order", so.name, "customer", primary_customer)
				
				# Update customer mappings
				mappings = frappe.get_all("Wix Customer Mapping", {"customer": duplicate_customer})
				for mapping in mappings:
					frappe.db.set_value("Wix Customer Mapping", mapping.name, "customer", primary_customer)
				
				# Delete duplicate customer
				frappe.delete_doc("Customer", duplicate_customer)
				
			except Exception as e:
				frappe.log_error(f"Failed to merge customer {duplicate_customer}: {str(e)}", "Wix Integration")
				continue
		
		return {"success": True, "message": f"Merged {len(duplicate_customers)} duplicate customers"}
		
	except Exception as e:
		frappe.log_error(f"Customer merge failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}

@frappe.whitelist()
def find_duplicate_customers():
	"""Find potential duplicate customers based on email and name"""
	try:
		# Find customers with same email
		email_duplicates = frappe.db.sql("""
			SELECT 
				c.email_id,
				GROUP_CONCAT(dl.link_name) as customers
			FROM `tabContact` c
			INNER JOIN `tabDynamic Link` dl ON c.name = dl.parent
			WHERE dl.link_doctype = 'Customer'
			AND c.email_id IS NOT NULL
			AND c.email_id != ''
			GROUP BY c.email_id
			HAVING COUNT(dl.link_name) > 1
		""", as_dict=True)
		
		# Find customers with same name
		name_duplicates = frappe.db.sql("""
			SELECT 
				customer_name,
				GROUP_CONCAT(name) as customers
			FROM `tabCustomer`
			WHERE customer_name IS NOT NULL
			AND customer_name != ''
			GROUP BY customer_name
			HAVING COUNT(name) > 1
		""", as_dict=True)
		
		return {
			"success": True,
			"email_duplicates": email_duplicates,
			"name_duplicates": name_duplicates
		}
		
	except Exception as e:
		frappe.log_error(f"Finding duplicate customers failed: {str(e)}", "Wix Integration")
		return {"success": False, "message": str(e)}