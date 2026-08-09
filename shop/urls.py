from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('TWIINA/COUNSEL/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', views.supplier_update, name='supplier_update'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),

    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/print/', views.print_inventory, name='print_inventory'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/toggle/', views.toggle_product_status, name='toggle_product_status'),

    # Stock In
    path('stock-in/', views.stock_in_list, name='stock_in_list'),
    path('stock-in/add/', views.stock_in_create, name='stock_in_create'),
    path('stock-in/<int:pk>/delete/', views.stock_in_delete, name='stock_in_delete'),

    # POS
    path('pos/', views.pos, name='pos'),
    path('pos/add-item/', views.pos_add_item, name='pos_add_item'),
    path('pos/remove-item/', views.pos_remove_item, name='pos_remove_item'),
    path('pos/update-qty/', views.pos_update_qty, name='pos_update_qty'),
    path('pos/complete/', views.pos_complete_sale, name='pos_complete_sale'),
    path('pos/clear/', views.pos_clear_cart, name='pos_clear_cart'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_update, name='expense_update'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # Stock Adjustments
    path('adjustments/', views.adjustment_list, name='adjustment_list'),
    path('adjustments/add/', views.adjustment_create, name='adjustment_create'),

    # Reports (role-aware)
    path('reports/', views.reports, name='reports'),
    path('reports/stock-history/', views.stock_history, name='stock_history'),
    path('reports/price-history/', views.price_history, name='price_history'),
    path('reports/stock-report/', views.stock_report, name='stock_report'),

    # Price Stickers (Admin only)
    path('products/stickers/', views.print_stickers, name='print_stickers'),

    # Users
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_update, name='user_update'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),

    # AJAX
    path('api/product/<int:pk>/', views.get_product_info, name='product_info'),
    path('api/products/search/', views.search_products, name='search_products'),

    # Online Store Admin
    path('store-settings/', views.store_settings, name='store_settings'),
    path('online-orders/', views.admin_online_orders, name='admin_online_orders'),
    path('online-orders/<int:pk>/complete/', views.admin_order_complete, name='admin_order_complete'),
    path('online-orders/<int:pk>/cancel/', views.admin_order_cancel, name='admin_order_cancel'),
    path('online-orders/<int:pk>/update-status/', views.admin_order_update_status, name='admin_order_update_status'),

    # Public Storefront (Main Channel directly at root '/')
    path('', views.store_home, name='store_home'),
    path('product/<int:pk>/', views.store_product_detail, name='store_product_detail'),
    path('cart/', views.store_cart, name='store_cart'),
    path('checkout/', views.store_checkout, name='store_checkout'),
    path('api/cart/', views.store_cart_api, name='store_cart_api'),

    # Backward compatibility mappings for /store/
    path('store/', views.store_home),
    path('store/product/<int:pk>/', views.store_product_detail),
    path('store/cart/', views.store_cart),
    path('store/checkout/', views.store_checkout),
]
