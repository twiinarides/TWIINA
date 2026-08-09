from django.contrib import admin
from .models import (
    UserProfile, Category, Supplier, Product, ProductTag, ProductImage,
    StockIn, Sale, SaleItem, Expense, StockAdjustment
)

admin.site.site_header = "TWIINA Electronics — Admin"
admin.site.site_title = "TWIINA Admin"
admin.site.index_title = "Backend Administration"


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['total']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'is_primary']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['sale_number', 'attendant', 'total_amount', 'date']
    list_filter = ['date', 'attendant']
    search_fields = ['sale_number']
    inlines = [SaleItemInline]
    readonly_fields = ['sale_number', 'total_amount', 'total_cost']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'get_selling_price_display', 'current_stock',
                    'is_active', 'is_on_flash_sale', 'is_featured', 'needs_fulfillment_display']
    list_filter = ['category', 'is_active', 'is_on_flash_sale', 'is_featured',
                   'pricing_mode', 'condition', 'source_type']
    search_fields = ['name', 'brand', 'model_number', 'barcode']
    list_editable = ['is_active', 'is_on_flash_sale', 'is_featured']
    inlines = [ProductImageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'brand', 'model_number', 'barcode',
                       'unit', 'description', 'image', 'tags')
        }),
        ('Pricing', {
            'fields': ('buying_price', 'pricing_mode', 'markup_percentage', 'direct_selling_price')
        }),
        ('Flash Sale', {
            'classes': ('collapse',),
            'fields': ('is_on_flash_sale', 'flash_sale_price', 'flash_sale_ends')
        }),
        ('Stock', {
            'fields': ('current_stock', 'reserved_stock', 'minimum_stock', 'warehouse_location')
        }),
        ('Product Details', {
            'classes': ('collapse',),
            'fields': ('condition', 'source_type', 'estimated_delivery_days', 'specifications')
        }),
        ('Visibility', {
            'fields': ('is_active', 'is_featured')
        }),
    )

    def needs_fulfillment_display(self, obj):
        return obj.needs_fulfillment
    needs_fulfillment_display.boolean = True
    needs_fulfillment_display.short_description = 'Needs Info'

    def get_selling_price_display(self, obj):
        return f"UGX {obj.get_selling_price():,.0f}"
    get_selling_price_display.short_description = 'Selling Price'


@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color']


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
