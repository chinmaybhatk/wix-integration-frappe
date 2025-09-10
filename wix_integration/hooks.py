from . import __version__ as app_version

app_name = "wix_integration"
app_title = "Wix Integration"
app_publisher = "KokoFresh"
app_description = "Wix ecommerce integration for unified CRM, inventory management, and order processing"
app_icon = "octicon octicon-plug"
app_color = "blue"
app_email = "admin@kokofresh.in"
app_license = "MIT"

# Document Events
doc_events = {
	"Item": {
		"after_insert": "wix_integration.api.products.sync_item_to_wix",
		"on_update": "wix_integration.api.products.update_item_in_wix",
		"validate": "wix_integration.api.products.validate_item_sync"
	},
	"Sales Order": {
		"on_submit": "wix_integration.api.orders.update_order_status_to_wix",
		"on_cancel": "wix_integration.api.orders.cancel_order_in_wix"
	},
	"Customer": {
		"after_insert": "wix_integration.api.customers.sync_customer_to_wix",
		"on_update": "wix_integration.api.customers.update_customer_in_wix"
	},
	"Stock Entry": {
		"on_submit": "wix_integration.api.products.update_inventory_to_wix"
	}
}

# Scheduled Tasks
scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"wix_integration.tasks.sync_inventory.sync_all_inventory"
		],
		"0 */2 * * *": [
			"wix_integration.tasks.sync_products.full_product_sync"
		],
		"0 0 * * *": [
			"wix_integration.tasks.sync_orders.process_pending_orders"
		]
	}
}

# Installation
fixtures = [
	"Custom Field",
	"Property Setter",
	"Custom Script"
]

# Required Apps
required_apps = ["frappe", "erpnext"]

# Boot Session
boot_session = "wix_integration.boot.boot_session"

# Website context
website_context = {
	"favicon": "/assets/wix_integration/images/favicon.ico",
	"splash_image": "/assets/wix_integration/images/splash.png"
}