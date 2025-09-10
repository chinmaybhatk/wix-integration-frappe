// Dashboard JavaScript
class WixDashboard {
    constructor() {
        this.charts = {};
        this.refreshInterval = 30000; // 30 seconds
        this.init();
    }

    init() {
        this.loadDashboardData();
        this.setupAutoRefresh();
        this.setupEventListeners();
        this.initializeCharts();
    }

    async loadDashboardData() {
        try {
            this.showLoading(false);
            
            // Load all dashboard data
            const [
                settingsData,
                productStats,
                orderStats,
                customerStats,
                recentActivity
            ] = await Promise.all([
                this.fetchData('/api/method/wix_integration.api.dashboard.get_integration_status'),
                this.fetchData('/api/method/wix_integration.api.products.get_product_sync_status'),
                this.fetchData('/api/method/wix_integration.api.orders.get_order_sync_status'),
                this.fetchData('/api/method/wix_integration.api.customers.get_customer_sync_status'),
                this.fetchData('/api/method/wix_integration.api.dashboard.get_recent_activity')
            ]);

            this.updateStatus(settingsData);
            this.updateProductStats(productStats);
            this.updateOrderStats(orderStats);
            this.updateCustomerStats(customerStats);
            this.updateRecentActivity(recentActivity);
            this.updateCharts();
            
            this.updateLastUpdated();
            
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            this.showError('Failed to load dashboard data');
        } finally {
            this.hideLoading();
        }
    }

    async fetchData(endpoint) {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`Failed to fetch ${endpoint}`);
        }
        const data = await response.json();
        return data.message || data;
    }

    updateStatus(data) {
        const statusIndicator = document.getElementById('integrationStatus');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');
        
        if (data.enabled) {
            statusDot.className = 'status-dot online';
            statusText.textContent = 'Online';
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = 'Offline';
        }

        // Update other status metrics
        document.getElementById('lastSyncTime').textContent = 
            data.last_sync_time ? this.formatDateTime(data.last_sync_time) : 'Never';
        
        document.getElementById('totalMappings').textContent = 
            (data.product_mappings || 0) + (data.customer_mappings || 0);
        
        document.getElementById('syncSuccessRate').textContent = 
            `${data.sync_success_rate || 0}%`;
    }

    updateProductStats(data) {
        document.getElementById('totalProducts').textContent = data.total || 0;
        document.getElementById('syncedProducts').textContent = data.synced || 0;
        document.getElementById('errorProducts').textContent = data.errors || 0;
        document.getElementById('pendingProducts').textContent = data.pending || 0;
        
        const progress = document.getElementById('productSyncProgress');
        progress.style.width = `${data.sync_rate || 0}%`;
    }

    updateOrderStats(data) {
        document.getElementById('totalOrders').textContent = data.total || 0;
        document.getElementById('processedOrders').textContent = data.synced || 0;
        document.getElementById('errorOrders').textContent = data.errors || 0;
        document.getElementById('recentOrders').textContent = data.recent || 0;
        
        const progress = document.getElementById('orderSyncProgress');
        progress.style.width = `${data.sync_rate || 0}%`;
    }

    updateCustomerStats(data) {
        document.getElementById('totalCustomers').textContent = data.total || 0;
        document.getElementById('syncedCustomers').textContent = data.synced || 0;
        document.getElementById('errorCustomers').textContent = data.errors || 0;
        document.getElementById('recentCustomers').textContent = data.recent || 0;
        
        const progress = document.getElementById('customerSyncProgress');
        progress.style.width = `${data.sync_rate || 0}%`;
    }

    updateRecentActivity(data) {
        const activityList = document.getElementById('recentActivity');
        
        if (!data || !data.activities || data.activities.length === 0) {
            activityList.innerHTML = '<div class="loading">No recent activity</div>';
            return;
        }

        const activityHTML = data.activities.map(activity => `
            <div class="activity-item">
                <div class="activity-icon ${activity.type}">
                    ${this.getActivityIcon(activity.type)}
                </div>
                <div class="activity-content">
                    <div class="activity-title">${activity.title}</div>
                    <div class="activity-time">${this.formatDateTime(activity.timestamp)}</div>
                </div>
            </div>
        `).join('');
        
        activityList.innerHTML = activityHTML;
    }

    getActivityIcon(type) {
        const icons = {
            success: '✓',
            error: '✗',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || 'ℹ';
    }

    initializeCharts() {
        // Sync Activity Chart
        const ctx1 = document.getElementById('syncActivityChart').getContext('2d');
        this.charts.syncActivity = new Chart(ctx1, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Products',
                        data: [],
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Orders',
                        data: [],
                        borderColor: '#2ecc71',
                        backgroundColor: 'rgba(46, 204, 113, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Customers',
                        data: [],
                        borderColor: '#f39c12',
                        backgroundColor: 'rgba(243, 156, 18, 0.1)',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });

        // Error Distribution Chart
        const ctx2 = document.getElementById('errorDistributionChart').getContext('2d');
        this.charts.errorDistribution = new Chart(ctx2, {
            type: 'doughnut',
            data: {
                labels: ['Products', 'Orders', 'Customers'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [
                        '#e74c3c',
                        '#f39c12',
                        '#9b59b6'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    async updateCharts() {
        try {
            // Get chart data
            const chartData = await this.fetchData('/api/method/wix_integration.api.dashboard.get_chart_data');
            
            // Update sync activity chart
            if (chartData.sync_activity) {
                this.charts.syncActivity.data.labels = chartData.sync_activity.labels;
                this.charts.syncActivity.data.datasets[0].data = chartData.sync_activity.products;
                this.charts.syncActivity.data.datasets[1].data = chartData.sync_activity.orders;
                this.charts.syncActivity.data.datasets[2].data = chartData.sync_activity.customers;
                this.charts.syncActivity.update();
            }

            // Update error distribution chart
            if (chartData.error_distribution) {
                this.charts.errorDistribution.data.datasets[0].data = [
                    chartData.error_distribution.products,
                    chartData.error_distribution.orders,
                    chartData.error_distribution.customers
                ];
                this.charts.errorDistribution.update();
            }

        } catch (error) {
            console.error('Error updating charts:', error);
        }
    }

    setupAutoRefresh() {
        setInterval(() => {
            this.loadDashboardData();
        }, this.refreshInterval);
    }

    setupEventListeners() {
        // Auto-refresh the page visibility API
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.loadDashboardData();
            }
        });
    }

    showLoading(fullScreen = true) {
        if (fullScreen) {
            document.getElementById('loadingOverlay').style.display = 'flex';
        }
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showError(message) {
        // You can implement a toast notification here
        console.error(message);
    }

    updateLastUpdated() {
        document.getElementById('lastUpdated').textContent = 
            new Date().toLocaleString();
    }

    formatDateTime(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleString();
    }
}

// Action Functions
async function triggerFullSync() {
    if (!confirm('This will trigger a full synchronization of all data. Continue?')) {
        return;
    }

    try {
        document.getElementById('loadingOverlay').style.display = 'flex';
        
        const response = await fetch('/api/method/wix_integration.doctype.wix_integration_settings.wix_integration_settings.sync_all_data', {
            method: 'POST'
        });
        
        if (response.ok) {
            alert('Full sync started successfully');
            dashboard.loadDashboardData();
        } else {
            alert('Failed to start full sync');
        }
    } catch (error) {
        alert('Error starting full sync: ' + error.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

async function retryFailedSyncs() {
    if (!confirm('This will retry all failed synchronizations. Continue?')) {
        return;
    }

    try {
        document.getElementById('loadingOverlay').style.display = 'flex';
        
        const [productResult, orderResult, customerResult] = await Promise.all([
            fetch('/api/method/wix_integration.api.products.retry_failed_product_syncs', { method: 'POST' }),
            fetch('/api/method/wix_integration.api.orders.retry_failed_order_syncs', { method: 'POST' }),
            fetch('/api/method/wix_integration.api.customers.retry_failed_customer_syncs', { method: 'POST' })
        ]);
        
        let message = 'Retry completed:\n';
        
        if (productResult.ok) {
            const data = await productResult.json();
            message += `Products: ${data.message.succeeded}/${data.message.retried} succeeded\n`;
        }
        
        if (orderResult.ok) {
            const data = await orderResult.json();
            message += `Orders: ${data.message.succeeded}/${data.message.retried} succeeded\n`;
        }
        
        if (customerResult.ok) {
            const data = await customerResult.json();
            message += `Customers: ${data.message.succeeded}/${data.message.retried} succeeded\n`;
        }
        
        alert(message);
        dashboard.loadDashboardData();
        
    } catch (error) {
        alert('Error retrying failed syncs: ' + error.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

function viewSettings() {
    window.open('/app/wix-integration-settings', '_blank');
}

function viewLogs() {
    window.open('/app/error-log', '_blank');
}

// Initialize dashboard when page loads
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new WixDashboard();
});