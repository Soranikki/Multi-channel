/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, useState, useRef } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

class MainDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        
        this.trendChartRef = useRef("trendChart");
        this.doughnutChartRef = useRef("doughnutChart");
        this.statusChartRef = useRef("statusChart");
        this.topProductChartRef = useRef("topProductChart");

        this.state = useState({
            data: {},
            updateTime: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
            dateFilter: '30d',
            currentDateLabel: '30 ngày qua',
            customStartDate: '',
            customEndDate: ''
        });

        this.charts = {};

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.fetchData('30d');
        });

        onMounted(() => {
            this.renderCharts();
        });
    }

    async fetchData(dateFilter = '30d', customStart = false, customEnd = false) {
        this.state.data = await this.orm.call("mc.dashboard", "get_dashboard_data", [dateFilter, customStart, customEnd]);
        this.state.updateTime = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    async changeDateFilter(filter, label) {
        this.state.dateFilter = filter;
        this.state.currentDateLabel = label;
        await this.fetchData(filter);
        this.reRenderCharts();
    }

    async applyCustomDate() {
        if (!this.state.customStartDate || !this.state.customEndDate) return;
        this.state.dateFilter = 'custom';
        this.state.currentDateLabel = `${this.state.customStartDate} - ${this.state.customEndDate}`;
        await this.fetchData('custom', this.state.customStartDate, this.state.customEndDate);
        this.reRenderCharts();
    }

    reRenderCharts() {
        // Destroy existing charts
        for (let key in this.charts) {
            if (this.charts[key]) {
                try { this.charts[key].destroy(); } catch (e) {}
            }
        }
        this.renderCharts();
    }

    renderCharts() {
        // Trend Chart
        try {
            if (this.trendChartRef.el && this.state.data.trend) {
                this.charts.trend = new Chart(this.trendChartRef.el, {
                    type: 'line',
                    data: {
                        labels: this.state.data.trend.labels,
                        datasets: [
                            {
                                label: 'Shopee',
                                data: this.state.data.trend.shopee,
                                borderColor: '#FF3B2F',
                                backgroundColor: 'rgba(255, 59, 47, 0.06)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true,
                                pointRadius: 0,
                                pointHoverRadius: 6,
                                pointBackgroundColor: '#ffffff',
                                pointBorderColor: '#FF3B2F',
                                pointBorderWidth: 2
                            },
                            {
                                label: 'TikTok Shop',
                                data: this.state.data.trend.tiktok,
                                borderColor: '#1f2937',
                                backgroundColor: 'transparent',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: false,
                                pointRadius: 0,
                                pointHoverRadius: 6,
                                pointBackgroundColor: '#ffffff',
                                pointBorderColor: '#1f2937',
                                pointBorderWidth: 2
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        plugins: {
                            legend: { 
                                position: 'top', 
                                align: 'end', 
                                labels: { 
                                    usePointStyle: true, 
                                    pointStyle: 'circle', 
                                    boxWidth: 8, 
                                    boxHeight: 8 
                                } 
                            },
                            tooltip: {
                                backgroundColor: '#ffffff',
                                titleColor: '#1f2937',
                                bodyColor: '#4b5563',
                                borderColor: 'rgba(0,0,0,0.08)',
                                borderWidth: 1,
                                padding: 12,
                                boxPadding: 6,
                                usePointStyle: true,
                                titleFont: { size: 14, weight: 'bold' },
                                bodyFont: { size: 13 },
                                callbacks: {
                                    title: (context) => {
                                        let label = context[0].label;
                                        let parts = label.split('-');
                                        return "Ngày " + (parts.length > 1 ? parts[1] : label);
                                    },
                                    label: (context) => {
                                        let val = context.raw;
                                        let formatted = val;
                                        if (val >= 1000000) {
                                            formatted = (val / 1000000).toFixed(1) + " Tr VNĐ";
                                        } else if (val >= 1000) {
                                            formatted = (val / 1000).toFixed(1) + " K VNĐ";
                                        } else {
                                            formatted = val + " đ";
                                        }
                                        return ` ${context.dataset.label}: ${formatted}`;
                                    }
                                }
                            }
                        },
                        scales: {
                            y: { 
                                beginAtZero: true, 
                                grid: { drawBorder: false, color: '#f3f4f6' },
                                ticks: {
                                    callback: function(value) {
                                        if (value >= 1000000) return (value / 1000000) + 'M';
                                        if (value >= 1000) return (value / 1000) + 'K';
                                        return value;
                                    }
                                }
                            },
                            x: { 
                                grid: { display: false },
                                ticks: {
                                    callback: function(val, index) {
                                        let label = this.getLabelForValue(val);
                                        if (!label) return val;
                                        let parts = label.split('-');
                                        return parts.length > 1 ? parseInt(parts[1], 10) : label;
                                    }
                                }
                            }
                        }
                    }
                });
            }
        } catch(e) { console.error("Error drawing trend chart:", e); }

        // Doughnut Chart (Revenue by Channel)
        try {
            if (this.doughnutChartRef.el && this.state.data.revenue_by_channel) {
                this.charts.doughnut = new Chart(this.doughnutChartRef.el, {
                    type: 'doughnut',
                    data: {
                        labels: this.state.data.revenue_by_channel.map(c => c.name),
                        datasets: [{
                            data: this.state.data.revenue_by_channel.map(c => c.raw_value),
                            backgroundColor: this.state.data.revenue_by_channel.map(c => c.color),
                            borderWidth: 2,
                            borderColor: '#ffffff',
                            hoverOffset: 15
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: {
                            padding: 20
                        },
                        cutout: '75%',
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: '#ffffff',
                                titleColor: '#1f2937',
                                bodyColor: '#4b5563',
                                borderColor: 'rgba(0,0,0,0.08)',
                                borderWidth: 1,
                                padding: 12,
                                boxPadding: 6,
                                usePointStyle: true,
                                titleFont: { size: 14, weight: 'bold' },
                                bodyFont: { size: 13 },
                                callbacks: {
                                    title: (context) => {
                                        return context[0].label;
                                    },
                                    label: (context) => {
                                        const channel = this.state.data.revenue_by_channel[context.dataIndex];
                                        return ` ${channel.name}: ${channel.value_str} đ (${channel.percentage})`;
                                    }
                                }
                            }
                        }
                    }
                });
            }
        } catch(e) { console.error("Error drawing doughnut chart:", e); }

        // Status Chart (Bar)
        try {
            if (this.statusChartRef.el && this.state.data.order_status) {
                this.charts.status = new Chart(this.statusChartRef.el, {
                    type: 'bar',
                    data: {
                        labels: this.state.data.order_status.labels,
                        datasets: [{
                            label: 'Orders',
                            data: this.state.data.order_status.data,
                            backgroundColor: ['#e2e8f0', '#bfdbfe', '#3b82f6', '#10b981', '#ef4444'],
                            borderRadius: 4,
                            barThickness: 30
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }
        } catch(e) { console.error("Error drawing status chart:", e); }

        // Top Product Chart (Horizontal Bar)
        try {
            if (this.topProductChartRef.el && this.state.data.top_products) {
                this.charts.topProduct = new Chart(this.topProductChartRef.el, {
                    type: 'bar',
                    data: {
                        labels: this.state.data.top_products.labels,
                        datasets: [{
                            label: 'Quantity Sold',
                            data: this.state.data.top_products.data,
                            backgroundColor: '#2563eb',
                            borderRadius: 4,
                            barThickness: 20
                        }]
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { beginAtZero: true, grid: { color: '#f3f4f6' } },
                            y: { grid: { display: false } }
                        }
                    }
                });
            }
        } catch(e) { console.error("Error drawing top product chart:", e); }
    }
}

MainDashboard.template = "mc_dashboard.MainDashboard";
registry.category("actions").add("mc_dashboard.main", MainDashboard);
