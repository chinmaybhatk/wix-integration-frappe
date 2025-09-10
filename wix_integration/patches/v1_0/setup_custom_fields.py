import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	"""Add custom fields to existing DocTypes for Wix integration"""
	
	custom_fields = {
		"Item": [
			{
				"fieldname": "wix_product_id",
				"label": "Wix Product ID",
				"fieldtype": "Data",
				"insert_after": "item_code",
				"read_only": 1,
				"description": "Wix Product ID for synchronization"
			},
			{
				"fieldname": "wix_sync_enabled",
				"label": "Enable Wix Sync",
				"fieldtype": "Check",
				"insert_after": "wix_product_id",
				"default": 1,
				"description": "Enable synchronization with Wix"
			},
			{
				"fieldname": "wix_last_sync",
				"label": "Last Wix Sync",
				"fieldtype": "Datetime",
				"insert_after": "wix_sync_enabled",
				"read_only": 1,
				"description": "Last synchronization timestamp"
			}
		],
		"Customer": [
			{
				"fieldname": "wix_customer_id",
				"label": "Wix Customer ID",
				"fieldtype": "Data",
				"insert_after": "customer_name",
				"read_only": 1,
				"description": "Wix Customer ID for synchronization"
			},
			{
				"fieldname": "wix_sync_enabled",
				"label": "Enable Wix Sync",
				"fieldtype": "Check",
				"insert_after": "wix_customer_id",
				"default": 1,
				"description": "Enable synchronization with Wix"
			},
			{
				"fieldname": "wix_last_sync",
				"label": "Last Wix Sync",
				"fieldtype": "Datetime",
				"insert_after": "wix_sync_enabled",
				"read_only": 1,
				"description": "Last synchronization timestamp"
			}
		],
		"Sales Order": [
			{
				"fieldname": "wix_order_id",
				"label": "Wix Order ID",
				"fieldtype": "Data",
				"insert_after": "customer",
				"read_only": 1,
				"description": "Wix Order ID for synchronization"
			},
			{
				"fieldname": "wix_order_number",
				"label": "Wix Order Number",
				"fieldtype": "Data",
				"insert_after": "wix_order_id",
				"read_only": 1,
				"description": "Wix Order Number"
			},
			{
				"fieldname": "wix_payment_status",
				"label": "Wix Payment Status",
				"fieldtype": "Select",
				"options": "Pending\nPaid\nPartially Paid\nRefunded\nCancelled",
				"insert_after": "wix_order_number",
				"read_only": 1,
				"description": "Payment status from Wix"
			},
			{
				"fieldname": "wix_fulfillment_status",
				"label": "Wix Fulfillment Status",
				"fieldtype": "Select",
				"options": "Pending\nProcessing\nFulfilled\nPartially Fulfilled\nCancelled",
				"insert_after": "wix_payment_status",
				"read_only": 1,
				"description": "Fulfillment status from Wix"
			}
		],
		"Delivery Note": [
			{
				"fieldname": "update_wix_fulfillment",
				"label": "Update Wix Fulfillment",
				"fieldtype": "Check",
				"insert_after": "lr_no",
				"default": 1,
				"description": "Update fulfillment status in Wix"
			}
		]
	}
	
	create_custom_fields(custom_fields)
	
	frappe.db.commit()
	print("Custom fields created successfully")