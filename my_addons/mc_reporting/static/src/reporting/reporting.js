/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onPatched, useState, useRef } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

class ReportingComponent extends Component {
    static template = "mc_reporting.Reporting";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.reportType = this.props.action.params.report_type || "sales_summary";
        this.chartRef = useRef("mainChart");

        this.state = useState({
            data: {},
            loading: true,
            reportType: this.reportType,
            dateFilter: "30d",
            platformFilter: "all",
            currentDateLabel: "30 ngày qua",
            currentPlatformLabel: "Tất cả kênh",
            customStartDate: "",
            customEndDate: "",
        });

        this.chart = null;
        this.platforms = [];
        this._pendingChart = false;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            this.platforms = await this.orm.searchRead("mc.channel", [], ["name", "code"]);
            await this.fetchData();
        });

        onMounted(() => {
            if (!this.state.loading && this.state.data) {
                this.renderCharts();
            }
        });

        onPatched(() => {
            if (this._pendingChart && this.chartRef.el) {
                this._pendingChart = false;
                this.reRenderChart();
            }
        });
    }

    get reportName() {
        const names = {
            sales_summary: "Tổng hợp Bán hàng",
            sales_channel: "Bán hàng theo Kênh",
            best_selling: "Sản phẩm Bán chạy",
            inventory: "Tồn kho",
            sync_status: "Đồng bộ Tồn kho",
            order_list: "Danh sách Đơn hàng",
        };
        return names[this.state.reportType] || this.state.reportType;
    }

    get updateTime() {
        return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    }

    async fetchData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("mc.report.engine", "get_report_data", [
                this.state.reportType,
                this.state.dateFilter,
                this.state.platformFilter,
                this.state.dateFilter === "custom" ? this.state.customStartDate : false,
                this.state.dateFilter === "custom" ? this.state.customEndDate : false,
            ]);
        } catch (e) {
            console.error("Report fetch error:", e);
        }
        this.state.loading = false;
    }

    async changeDateFilter(filter, label) {
        this.state.dateFilter = filter;
        this.state.currentDateLabel = label;
        await this.fetchData();
        this._pendingChart = true;
    }

    async changePlatform(platform, label) {
        this.state.platformFilter = platform;
        this.state.currentPlatformLabel = label;
        await this.fetchData();
        this._pendingChart = true;
    }

    async applyCustomDate() {
        if (!this.state.customStartDate || !this.state.customEndDate) return;
        this.state.dateFilter = "custom";
        this.state.currentDateLabel = `${this.state.customStartDate} - ${this.state.customEndDate}`;
        await this.fetchData();
        this._pendingChart = true;
    }

    reRenderChart() {
        if (this.chart) {
            try { this.chart.destroy(); } catch (e) {}
            this.chart = null;
        }
        this.renderCharts();
    }

    renderCharts() {
        const data = this.state.data;
        if (!data) return;
        try {
            switch (this.state.reportType) {
                case "sales_summary":
                    this._renderTrendChart(data.trend);
                    break;
                case "sales_channel":
                    this._renderChannelChart(data.chart);
                    break;
                case "best_selling":
                    this._renderBestSellingChart(data.chart);
                    break;
                case "inventory":
                    this._renderStockStatusChart(data.stock_status);
                    break;
                case "sync_status":
                    this._renderSyncPieChart(data.chart);
                    break;
                case "order_list":
                    this._renderOrderStatusChart(data.order_status);
                    break;
            }
        } catch (e) {
            console.error("Chart render error:", e);
        }
    }

    _makeTrendChart(canvas, chartData) {
        const ds = chartData.datasets || [];
        return new Chart(canvas, {
            type: "line",
            data: {
                labels: chartData.labels,
                datasets: ds.map((d, i) => ({
                    label: d.label,
                    data: d.data,
                    borderColor: ["#2563eb", "#10b981", "#f59e0b"][i % 3],
                    backgroundColor: ["rgba(37,99,235,0.06)", "rgba(16,185,129,0.06)", "rgba(245,158,11,0.06)"][i % 3],
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { position: "top", align: "end", labels: { usePointStyle: true, boxWidth: 8 } },
                    tooltip: {
                        backgroundColor: "#fff", titleColor: "#1f2937", bodyColor: "#4b5563",
                        borderColor: "rgba(0,0,0,0.08)", borderWidth: 1, padding: 12,
                        callbacks: {
                            label: (ctx) => {
                                const v = ctx.raw;
                                return ` ${ctx.dataset.label}: ${v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : v}`;
                            },
                        },
                    },
                },
                scales: {
                    y: { beginAtZero: true, grid: { color: "#f3f4f6" }, ticks: { callback: (v) => v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : v } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    _renderTrendChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        this.chart = this._makeTrendChart(this.chartRef.el, chartData);
    }

    _renderChannelChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        const channels = this.state.data.channels || [];
        const colors = chartData.labels.map(lb => {
            const ch = channels.find(c => c.name === lb);
            return ch ? ch.color : "#6b7280";
        });
        this.chart = new Chart(this.chartRef.el, {
            type: "bar",
            data: {
                labels: chartData.labels,
                datasets: [{ label: "Doanh thu", data: chartData.revenue, backgroundColor: colors, borderRadius: 6, barThickness: 40 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "#f3f4f6" }, ticks: { callback: (v) => v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "K" : v } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    _renderBestSellingChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        const labels = (chartData.labels || []).slice(0, 10);
        const qty = (chartData.qty || []).slice(0, 10);
        this.chart = new Chart(this.chartRef.el, {
            type: "bar",
            data: { labels, datasets: [{ label: "SL bán", data: qty, backgroundColor: "#2563eb", borderRadius: 4, barThickness: 20 }] },
            options: {
                indexAxis: "y", responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { beginAtZero: true, grid: { color: "#f3f4f6" } },
                    y: { grid: { display: false } },
                },
            },
        });
    }

    _renderStockStatusChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        this.chart = new Chart(this.chartRef.el, {
            type: "doughnut",
            data: {
                labels: chartData.labels,
                datasets: [{ data: chartData.data, backgroundColor: ["#10b981", "#f59e0b", "#ef4444"], borderWidth: 2, borderColor: "#fff" }],
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: "70%",
                plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } } },
            },
        });
    }

    _renderSyncPieChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        this.chart = new Chart(this.chartRef.el, {
            type: "doughnut",
            data: {
                labels: chartData.labels,
                datasets: [{ data: chartData.data, backgroundColor: ["#10b981", "#f59e0b", "#ef4444"], borderWidth: 2, borderColor: "#fff" }],
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: "70%",
                plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } } },
            },
        });
    }

    _renderOrderStatusChart(chartData) {
        if (!this.chartRef.el || !chartData) return;
        this.chart = new Chart(this.chartRef.el, {
            type: "bar",
            data: {
                labels: chartData.labels,
                datasets: [{ label: "Đơn hàng", data: chartData.data, backgroundColor: ["#3b82f6", "#10b981", "#ef4444"], borderRadius: 6, barThickness: 40 }],
            },
            options: { responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "#f3f4f6" } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    exportPDF() {
        const p = this.state;
        const q = new URLSearchParams({ date_range: p.dateFilter, platform: p.platformFilter, custom_start: p.customStartDate, custom_end: p.customEndDate });
        window.open(`/mc/report/pdf/${p.reportType}?${q}`, "_blank");
    }

    exportXLSX() {
        const p = this.state;
        const q = new URLSearchParams({ date_range: p.dateFilter, platform: p.platformFilter, custom_start: p.customStartDate, custom_end: p.customEndDate });
        window.open(`/mc/report/xlsx/${p.reportType}?${q}`, "_blank");
    }
}

registry.category("actions").add("mc_reporting.report", ReportingComponent);
