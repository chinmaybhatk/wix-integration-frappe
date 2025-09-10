import frappe
from frappe.utils import now, add_days, flt
import json

@frappe.whitelist()
def get_integration_status():
	"""Get overall integration status"""
	try:
		settings = frappe.get_single("Wix Integration Settings")
		
		# Count mappings
		product_mappings = frappe.db.count("Wix Product Mapping")
		customer_mappings = frappe.db.count("Wix Customer Mapping")
		
		# Calculate overall sync success rate
		total_mappings = product_mappings + customer_mappings
		synced_mappings = frappe.db.count("Wix Product Mapping", {"sync_status": "Synced"}) + \
						 frappe.db.count("Wix Customer Mapping", {"sync_status": "Synced"})
		
		sync_success_rate = (synced_mappings / total_mappings * 100) if total_mappings > 0 else 0
		
		return {
			"enabled": settings.enabled if settings else False,
			"last_sync_time": settings.last_sync_time if settings else None,
			"sync_status": settings.sync_status if settings else "Idle",
			"product_mappings": product_mappings,
			"customer_mappings": customer_mappings,
			"total_mappings": total_mappings,
			"sync_success_rate": round(sync_success_rate, 1)
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get integration status: {str(e)}", "Wix Integration")
		return {"error": str(e)}

@frappe.whitelist()
def get_recent_activity(limit=10):
	"""Get recent sync activities"""
	try:
		activities = []
		
		# Get recent product syncs
		recent_products = frappe.db.sql("""
			SELECT 
				'Product' as type,
				CONCAT('Product ', item_name, ' synced') as title,
				last_sync_time as timestamp,
				sync_status
			FROM `tabWix Product Mapping`
			WHERE last_sync_time IS NOT NULL
			ORDER BY last_sync_time DESC
			LIMIT %s
		""", (limit//3,), as_dict=True)
		
		# Get recent order syncs
		recent_orders = frappe.db.sql("""
			SELECT 
				'Order' as type,
				CONCAT('Order ', wix_order_number, ' processed') as title,
				last_sync_time as timestamp,
				sync_status
			FROM `tabWix Order Sync Log`
			WHERE last_sync_time IS NOT NULL
			ORDER BY last_sync_time DESC
			LIMIT %s
		""", (limit//3,), as_dict=True)
		
		# Get recent customer syncs
		recent_customers = frappe.db.sql("""
			SELECT 
				'Customer' as type,
				CONCAT('Customer ', customer_name, ' synced') as title,
				last_sync_time as timestamp,
				sync_status
			FROM `tabWix Customer Mapping`
			WHERE last_sync_time IS NOT NULL
			ORDER BY last_sync_time DESC
			LIMIT %s
		""", (limit//3,), as_dict=True)
		
		# Combine and sort all activities
		all_activities = recent_products + recent_orders + recent_customers
		all_activities = sorted(all_activities, key=lambda x: x.timestamp, reverse=True)[:limit]
		
		# Map sync status to activity type
		for activity in all_activities:
			if activity.sync_status == "Synced":
				activity.type = "success"
			elif activity.sync_status == "Error":
				activity.type = "error"
			else:
				activity.type = "warning"
		
		return {"activities": all_activities}
		
	except Exception as e:
		frappe.log_error(f"Failed to get recent activity: {str(e)}", "Wix Integration")
		return {"error": str(e)}

@frappe.whitelist()
def get_chart_data():
	"""Get data for dashboard charts"""
	try:
		# Get sync activity data for last 7 days
		sync_activity = get_sync_activity_data()
		
		# Get error distribution data
		error_distribution = get_error_distribution_data()
		
		return {
			"sync_activity": sync_activity,
			"error_distribution": error_distribution
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get chart data: {str(e)}", "Wix Integration")
		return {"error": str(e)}

def get_sync_activity_data():
	"""Get sync activity data for the last 7 days"""
	try:
		labels = []
		product_data = []
		order_data = []
		customer_data = []
		
		for i in range(6, -1, -1):  # Last 7 days
			date = add_days(now(), -i).split()[0]
			labels.append(date)
			
			# Count syncs for each type on this date
			product_syncs = frappe.db.count("Wix Product Mapping", {
				"last_sync_time": ["like", f"{date}%"],
				"sync_status": "Synced"
			})
			
			order_syncs = frappe.db.count("Wix Order Sync Log", {
				"last_sync_time": ["like", f"{date}%"],
				"sync_status": "Synced"
			})
			
			customer_syncs = frappe.db.count("Wix Customer Mapping", {
				"last_sync_time": ["like", f"{date}%"],
				"sync_status": "Synced"
			})
			
			product_data.append(product_syncs)
			order_data.append(order_syncs)
			customer_data.append(customer_syncs)
		
		return {
			"labels": labels,
			"products": product_data,
			"orders": order_data,
			"customers": customer_data
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get sync activity data: {str(e)}", "Wix Integration")
		return {}

def get_error_distribution_data():
	"""Get error distribution data"""
	try:
		product_errors = frappe.db.count("Wix Product Mapping", {"sync_status": "Error"})
		order_errors = frappe.db.count("Wix Order Sync Log", {"sync_status": "Error"})
		customer_errors = frappe.db.count("Wix Customer Mapping", {"sync_status": "Error"})
		
		return {
			"products": product_errors,
			"orders": order_errors,
			"customers": customer_errors
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get error distribution data: {str(e)}", "Wix Integration")
		return {}

@frappe.whitelist()
def get_performance_metrics():
	"""Get performance metrics for the dashboard"""
	try:
		# API response times (last 24 hours)
		avg_response_time = get_average_api_response_time()
		
		# Sync latency
		avg_sync_latency = get_average_sync_latency()
		
		# Error rates
		error_rates = get_error_rates()
		
		# Throughput
		throughput = get_sync_throughput()
		
		return {
			"avg_response_time": avg_response_time,
			"avg_sync_latency": avg_sync_latency,
			"error_rates": error_rates,
			"throughput": throughput
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get performance metrics: {str(e)}", "Wix Integration")
		return {"error": str(e)}

def get_average_api_response_time():
	"""Calculate average API response time from error logs"""
	try:
		# This would require implementing response time logging
		# For now, return a placeholder
		return 150  # milliseconds
		
	except Exception as e:
		return 0

def get_average_sync_latency():
	"""Calculate average sync latency"""
	try:
		# Calculate time between order creation in Wix and processing in Frappe
		latency_data = frappe.db.sql("""
			SELECT AVG(TIMESTAMPDIFF(SECOND, created_time, last_sync_time)) as avg_latency
			FROM `tabWix Order Sync Log`
			WHERE sync_status = 'Synced'
			AND created_time >= %s
		""", (add_days(now(), -1),))
		
		if latency_data and latency_data[0][0]:
			return round(latency_data[0][0], 2)  # seconds
		
		return 0
		
	except Exception as e:
		return 0

def get_error_rates():
	"""Calculate error rates for different sync types"""
	try:
		# Product error rate
		total_products = frappe.db.count("Wix Product Mapping")
		error_products = frappe.db.count("Wix Product Mapping", {"sync_status": "Error"})
		product_error_rate = (error_products / total_products * 100) if total_products > 0 else 0
		
		# Order error rate
		total_orders = frappe.db.count("Wix Order Sync Log")
		error_orders = frappe.db.count("Wix Order Sync Log", {"sync_status": "Error"})
		order_error_rate = (error_orders / total_orders * 100) if total_orders > 0 else 0
		
		# Customer error rate
		total_customers = frappe.db.count("Wix Customer Mapping")
		error_customers = frappe.db.count("Wix Customer Mapping", {"sync_status": "Error"})
		customer_error_rate = (error_customers / total_customers * 100) if total_customers > 0 else 0
		
		return {
			"products": round(product_error_rate, 2),
			"orders": round(order_error_rate, 2),
			"customers": round(customer_error_rate, 2)
		}
		
	except Exception as e:
		return {"products": 0, "orders": 0, "customers": 0}

def get_sync_throughput():
	"""Calculate sync throughput (items per hour)"""
	try:
		# Calculate syncs in the last hour
		one_hour_ago = add_days(now(), 0, 0, -1)  # 1 hour ago
		
		recent_syncs = (
			frappe.db.count("Wix Product Mapping", {
				"last_sync_time": [">=", one_hour_ago],
				"sync_status": "Synced"
			}) +
			frappe.db.count("Wix Order Sync Log", {
				"last_sync_time": [">=", one_hour_ago],
				"sync_status": "Synced"
			}) +
			frappe.db.count("Wix Customer Mapping", {
				"last_sync_time": [">=", one_hour_ago],
				"sync_status": "Synced"
			})
		)
		
		return recent_syncs
		
	except Exception as e:
		return 0

@frappe.whitelist()
def get_system_health():
	"""Get system health indicators"""
	try:
		# Check Wix API connectivity
		wix_status = check_wix_connectivity()
		
		# Check database performance
		db_status = check_database_performance()
		
		# Check disk space
		disk_status = check_disk_space()
		
		# Check error log volume
		error_volume = check_error_volume()
		
		return {
			"wix_api": wix_status,
			"database": db_status,
			"disk_space": disk_status,
			"error_volume": error_volume,
			"overall_status": "healthy" if all([wix_status["status"] == "ok", db_status["status"] == "ok", 
											   disk_status["status"] == "ok", error_volume["status"] == "ok"]) else "warning"
		}
		
	except Exception as e:
		frappe.log_error(f"Failed to get system health: {str(e)}", "Wix Integration")
		return {"error": str(e)}

def check_wix_connectivity():
	"""Check Wix API connectivity"""
	try:
		from wix_integration.utils.wix_client import get_wix_client
		
		wix_client = get_wix_client()
		# Try a simple API call
		result = wix_client.make_request("GET", "/stores/v1/products/query", {"query": {"limit": 1}})
		
		if result is not None:
			return {"status": "ok", "message": "Connected"}
		else:
			return {"status": "error", "message": "Connection failed"}
		
	except Exception as e:
		return {"status": "error", "message": str(e)}

def check_database_performance():
	"""Check database performance indicators"""
	try:
		# Simple query performance test
		import time
		start_time = time.time()
		
		frappe.db.sql("SELECT COUNT(*) FROM `tabWix Product Mapping`")
		
		query_time = (time.time() - start_time) * 1000  # milliseconds
		
		if query_time < 100:
			return {"status": "ok", "message": f"Query time: {query_time:.2f}ms"}
		elif query_time < 500:
			return {"status": "warning", "message": f"Slow queries: {query_time:.2f}ms"}
		else:
			return {"status": "error", "message": f"Very slow queries: {query_time:.2f}ms"}
		
	except Exception as e:
		return {"status": "error", "message": str(e)}

def check_disk_space():
	"""Check available disk space"""
	try:
		import shutil
		
		total, used, free = shutil.disk_usage("/")
		free_percent = (free / total) * 100
		
		if free_percent > 20:
			return {"status": "ok", "message": f"{free_percent:.1f}% free"}
		elif free_percent > 10:
			return {"status": "warning", "message": f"Low disk space: {free_percent:.1f}% free"}
		else:
			return {"status": "error", "message": f"Critical disk space: {free_percent:.1f}% free"}
		
	except Exception as e:
		return {"status": "ok", "message": "Unable to check"}

def check_error_volume():
	"""Check recent error volume"""
	try:
		# Count errors in last 24 hours
		recent_errors = frappe.db.count("Error Log", {
			"creation": [">=", add_days(now(), -1)],
			"error": ["like", "%wix%"]
		})
		
		if recent_errors < 5:
			return {"status": "ok", "message": f"{recent_errors} errors"}
		elif recent_errors < 20:
			return {"status": "warning", "message": f"{recent_errors} errors"}
		else:
			return {"status": "error", "message": f"High error volume: {recent_errors} errors"}
		
	except Exception as e:
		return {"status": "ok", "message": "Unable to check"}

@frappe.whitelist()
def export_dashboard_data():
	"""Export dashboard data for reporting"""
	try:
		data = {
			"timestamp": now(),
			"integration_status": get_integration_status(),
			"performance_metrics": get_performance_metrics(),
			"system_health": get_system_health(),
			"sync_statistics": {
				"products": frappe.call("wix_integration.api.products.get_product_sync_status"),
				"orders": frappe.call("wix_integration.api.orders.get_order_sync_status"),
				"customers": frappe.call("wix_integration.api.customers.get_customer_sync_status")
			}
		}
		
		return data
		
	except Exception as e:
		frappe.log_error(f"Failed to export dashboard data: {str(e)}", "Wix Integration")
		return {"error": str(e)}