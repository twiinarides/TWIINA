from django.contrib import admin
from .models import (
    UserProfile, Category, Supplier, Product, StockIn,
    Sale, SaleItem, Expense, StockAdjustment
)

admin.site.site_header = "TWIINA Electronics — Admin"
admin.site.site_title = "TWIINA Admin"
admin.site.index_title = "Backend Administration"


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['total']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['sale_number', 'attendant', 'total_amount', 'date']
    list_filter = ['date', 'attendant']
    search_fields = ['sale_number']
    inlines = [SaleItemInline]
    readonly_fields = ['sale_number', 'total_amount', 'total_cost']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'buying_price', 'pricing_mode', 'current_stock', 'is_active']
    list_filter = ['category', 'is_active', 'pricing_mode']
    search_fields = ['name', 'brand', 'model_number']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email', 'is_active']
    search_fields = ['name', 'phone']


@admin.register(StockIn)
class StockInAdmin(admin.ModelAdmin):
    list_display = ['product', 'supplier', 'quantity', 'buying_price_per_unit', 'total_cost', 'date_received']
    list_filter = ['date_received', 'supplier']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'amount', 'date', 'recorded_by']
    list_filter = ['category', 'date']


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['product', 'adjustment_type', 'quantity', 'reason', 'date']


admin.site.register(UserProfile)
admin.site.register(Category)
