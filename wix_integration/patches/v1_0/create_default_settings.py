import frappe

def execute():
	"""Create default Wix Integration Settings"""
	
	if not frappe.db.exists("Wix Integration Settings", "Wix Integration Settings"):
		settings = frappe.get_doc({
			"doctype": "Wix Integration Settings",
			"title": "Wix Integration Settings",
			"enabled": 0,
			"sync_products": 1,
			"sync_inventory": 1,
			"sync_orders": 1,
			"sync_customers": 1,
			"auto_create_items": 1,
			"auto_create_customers": 1,
			"inventory_sync_frequency": 5,
			"sync_status": "Idle"
		})
		settings.insert()
		frappe.db.commit()
		print("Default Wix Integration Settings created")
	else:
		print("Wix Integration Settings already exists")