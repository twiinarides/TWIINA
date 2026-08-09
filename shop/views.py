import json
from io import BytesIO
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta, date
import calendar

from .models import (
    Product, Category, Supplier, StockIn, Sale, SaleItem,
    Expense, StockAdjustment, UserProfile, StoreSettings, OnlineOrder, OnlineOrderItem,
    StockMovement, PriceHistory
)
from .forms import (
    LoginForm, CategoryForm, SupplierForm, ProductForm, StockInForm,
    ExpenseForm, StockAdjustmentForm, AttendantCreationForm, AttendantUpdateForm, StoreSettingsForm
)
from .decorators import admin_required, attendant_or_admin_required


# ─────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password']
        )
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'shop/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    try:
        if request.user.profile.is_admin():
            return admin_dashboard(request)
    except Exception:
        pass
    return attendant_dashboard(request)


@login_required
def admin_dashboard(request):
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    last_30 = today - timedelta(days=30)

    # Sales stats
    total_sales = Sale.objects.aggregate(
        revenue=Sum('total_amount'), cost=Sum('total_cost')
    )
    total_revenue = total_sales['revenue'] or Decimal('0')
    total_cost_of_goods = total_sales['cost'] or Decimal('0')
    gross_profit = total_revenue - total_cost_of_goods

    total_expenses = Expense.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    net_profit = gross_profit - total_expenses

    today_sales = Sale.objects.filter(date__date=today)
    today_revenue = today_sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    today_profit = today_sales.aggregate(
        p=Sum(F('total_amount') - F('total_cost'))
    )['p'] or Decimal('0')

    month_sales = Sale.objects.filter(date__date__gte=this_month_start)
    month_revenue = month_sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    month_expenses = Expense.objects.filter(date__gte=this_month_start).aggregate(
        t=Sum('amount')
    )['t'] or Decimal('0')

    # Stock stats
    low_stock_products = Product.objects.filter(
        current_stock__lte=F('minimum_stock'), is_active=True
    ).order_by('current_stock')[:10]
    total_products = Product.objects.filter(is_active=True).count()
    out_of_stock = Product.objects.filter(current_stock=0, is_active=True).count()
    stock_value = Product.objects.filter(is_active=True).aggregate(
        v=Sum(F('current_stock') * F('buying_price'))
    )['v'] or Decimal('0')

    active_products = Product.objects.filter(is_active=True)
    total_stock_items = active_products.aggregate(t=Sum('current_stock'))['t'] or 0
    expected_profit = sum((p.potential_revenue() - p.stock_value()) for p in active_products) if active_products else Decimal('0')

    # Top selling products
    top_products = SaleItem.objects.values(
        'product__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum('total')
    ).order_by('-total_qty')[:8]

    # Monthly chart data (last 6 months)
    monthly_data = []
    for i in range(5, -1, -1):
        dt = today - timedelta(days=30 * i)
        m_start = dt.replace(day=1)
        if dt.month == 12:
            m_end = dt.replace(year=dt.year + 1, month=1, day=1)
        else:
            m_end = dt.replace(month=dt.month + 1, day=1)
        m_sales = Sale.objects.filter(date__date__gte=m_start, date__date__lt=m_end)
        m_rev = m_sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
        m_cost = m_sales.aggregate(t=Sum('total_cost'))['t'] or Decimal('0')
        m_exp = Expense.objects.filter(date__gte=m_start, date__lt=m_end).aggregate(
            t=Sum('amount')
        )['t'] or Decimal('0')
        monthly_data.append({
            'month': m_start.strftime('%b %Y'),
            'revenue': float(m_rev),
            'profit': float(m_rev - m_cost - m_exp),
        })

    # Total losses from adjustments
    total_losses = StockAdjustment.objects.filter(adjustment_type='loss').aggregate(
        v=Sum('estimated_value')
    )['v'] or Decimal('0')

    # Recent sales
    recent_sales = Sale.objects.select_related('attendant').order_by('-date')[:10]

    # ── OMNI-CHANNEL ANALYTICS ──
    # Online revenue from completed orders
    online_revenue = OnlineOrder.objects.filter(status='COMPLETED').aggregate(
        t=Sum('total_amount')
    )['t'] or Decimal('0')
    instore_revenue = total_revenue - online_revenue

    # Pending online orders count
    pending_orders = OnlineOrder.objects.filter(status__in=['PENDING', 'READY_FOR_PICKUP', 'OUT_FOR_DELIVERY']).count()

    # Omni-stock alerts: products where available_stock <= minimum_stock
    omni_alerts = []
    for p in Product.objects.filter(is_active=True):
        avail = p.available_stock()
        if avail <= p.minimum_stock and p.current_stock > 0:
            omni_alerts.append({
                'name': p.name,
                'current_stock': p.current_stock,
                'reserved': p.reserved_stock,
                'available': avail,
                'minimum': p.minimum_stock,
            })

    context = {
        'total_revenue': total_revenue,
        'gross_profit': gross_profit,
        'net_profit': net_profit,
        'total_expenses': total_expenses,
        'today_revenue': today_revenue,
        'today_profit': today_profit,
        'today_sales_num': today_sales.count(),
        'month_revenue': month_revenue,
        'month_expenses': month_expenses,
        'low_stock_products': low_stock_products,
        'total_products': total_products,
        'out_of_stock': out_of_stock,
        'stock_value': stock_value,
        'top_products': list(top_products),
        'monthly_data': json.dumps(monthly_data),
        'total_losses': total_losses,
        'recent_sales': recent_sales,
        'total_sales_count': Sale.objects.count(),
        'total_stock_items': total_stock_items,
        'expected_profit': expected_profit,
        # Omni-channel
        'instore_revenue': instore_revenue,
        'online_revenue': online_revenue,
        'pending_orders': pending_orders,
        'omni_alerts': omni_alerts,
    }
    return render(request, 'shop/dashboard_admin.html', context)


@login_required
def attendant_dashboard(request):
    today = timezone.now().date()
    my_sales_today = Sale.objects.filter(attendant=request.user, date__date=today)
    my_revenue_today = my_sales_today.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    my_all_sales = Sale.objects.filter(attendant=request.user)
    my_total_revenue = my_all_sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    recent_sales = my_all_sales.order_by('-date')[:10]
    context = {
        'my_sales_today': my_sales_today.count(),
        'my_revenue_today': my_revenue_today,
        'my_total_sales': my_all_sales.count(),
        'my_total_revenue': my_total_revenue,
        'recent_sales': recent_sales,
    }
    return render(request, 'shop/dashboard_attendant.html', context)


# ─────────────────────────────────────────────────────────────
# CATEGORIES (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def category_list(request):
    categories = Category.objects.annotate(product_count=Count('product'))
    return render(request, 'shop/categories/list.html', {'categories': categories})


@admin_required
def category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Category added successfully.')
        return redirect('category_list')
    return render(request, 'shop/categories/form.html', {'form': form, 'title': 'Add Category'})


@admin_required
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Category updated.')
        return redirect('category_list')
    return render(request, 'shop/categories/form.html', {'form': form, 'title': 'Edit Category', 'obj': category})


@admin_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category deleted.')
        return redirect('category_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': category, 'obj_name': 'Category', 'cancel_url': 'category_list'
    })


# ─────────────────────────────────────────────────────────────
# SUPPLIERS (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def supplier_list(request):
    q = request.GET.get('q', '')
    suppliers = Supplier.objects.all()
    if q:
        suppliers = suppliers.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(contact_person__icontains=q))
    return render(request, 'shop/suppliers/list.html', {'suppliers': suppliers, 'q': q})


@admin_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Supplier added successfully.')
        return redirect('supplier_list')
    return render(request, 'shop/suppliers/form.html', {'form': form, 'title': 'Add Supplier'})


@admin_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    stock_ins = supplier.stockin_set.select_related('product').order_by('-date_received')[:20]
    return render(request, 'shop/suppliers/detail.html', {
        'supplier': supplier,
        'stock_ins': stock_ins,
    })


@admin_required
def supplier_update(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    form = SupplierForm(request.POST or None, instance=supplier)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Supplier updated.')
        return redirect('supplier_list')
    return render(request, 'shop/suppliers/form.html', {'form': form, 'title': 'Edit Supplier', 'obj': supplier})


@admin_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.delete()
        messages.success(request, 'Supplier deleted.')
        return redirect('supplier_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': supplier, 'obj_name': 'Supplier', 'cancel_url': 'supplier_list'
    })


# ─────────────────────────────────────────────────────────────
# PRODUCTS (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def product_list(request):
    q = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    stock_filter = request.GET.get('stock', '')
    products = Product.objects.select_related('category').filter(is_active=True)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(model_number__icontains=q))
    if category_id:
        products = products.filter(category_id=category_id)
    if stock_filter == 'low':
        products = products.filter(current_stock__lte=F('minimum_stock'))
    elif stock_filter == 'out':
        products = products.filter(current_stock=0)
    categories = Category.objects.all()
    return render(request, 'shop/products/list.html', {
        'products': products,
        'categories': categories,
        'q': q,
        'category_id': category_id,
        'stock_filter': stock_filter,
    })


@admin_required
def print_inventory(request):
    products = Product.objects.select_related('category').filter(is_active=True).order_by('category__name', 'name')
    return render(request, 'shop/products/print_inventory.html', {'products': products, 'date': timezone.now()})


@admin_required
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        
        # Log initial stock if any
        if product.current_stock > 0:
            StockMovement.objects.create(
                product=product,
                action_type='INITIAL_STOCK',
                quantity_changed=product.current_stock,
                unit_cost_at_time=product.buying_price,
                selling_price_at_time=product.get_selling_price(),
                reference='System Initialization',
                user=request.user
            )

        messages.success(request, 'Product added successfully.')
        return redirect('product_list')
    return render(request, 'shop/products/form.html', {'form': form, 'title': 'Add Product'})


@admin_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    stock_ins = product.stock_ins.select_related('supplier', 'received_by').order_by('-date_received')[:10]
    recent_sales = SaleItem.objects.filter(product=product).select_related('sale').order_by('-sale__date')[:10]
    adjustments = product.adjustments.select_related('recorded_by').order_by('-date')[:10]
    total_sold = SaleItem.objects.filter(product=product).aggregate(t=Sum('quantity'))['t'] or 0
    total_revenue_from = SaleItem.objects.filter(product=product).aggregate(t=Sum('total'))['t'] or Decimal('0')
    return render(request, 'shop/products/detail.html', {
        'product': product,
        'stock_ins': stock_ins,
        'recent_sales': recent_sales,
        'adjustments': adjustments,
        'total_sold': total_sold,
        'total_revenue_from': total_revenue_from,
    })


@admin_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    old_buying_price = product.buying_price
    old_selling_price = product.get_selling_price()

    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        
        new_buying_price = product.buying_price
        new_selling_price = product.get_selling_price()
        
        # Log price change if prices changed
        if old_buying_price != new_buying_price or old_selling_price != new_selling_price:
            PriceHistory.objects.create(
                product=product,
                old_buying_price=old_buying_price,
                new_buying_price=new_buying_price,
                old_selling_price=old_selling_price,
                new_selling_price=new_selling_price,
                user=request.user
            )

        messages.success(request, 'Product updated.')
        return redirect('product_list')
    return render(request, 'shop/products/form.html', {'form': form, 'title': 'Edit Product', 'obj': product})


@admin_required
def toggle_product_status(request, pk):
    if request.method == 'POST':
        product = get_object_or_404(Product, pk=pk)
        field = request.POST.get('field')
        
        if field == 'is_on_flash_sale':
            product.is_on_flash_sale = not product.is_on_flash_sale
            if product.is_on_flash_sale:
                price = request.POST.get('price')
                ends = request.POST.get('ends')
                if price and ends:
                    product.flash_sale_price = price
                    product.flash_sale_ends = ends
            else:
                product.flash_sale_price = None
                product.flash_sale_ends = None
        elif field == 'is_featured':
            product.is_featured = not product.is_featured
            
        product.save()
        return JsonResponse({'success': True, 'state': getattr(product, field)})
    return JsonResponse({'success': False})


@admin_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.is_active = False
        product.save()
        messages.success(request, 'Product removed from inventory.')
        return redirect('product_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': product, 'obj_name': 'Product', 'cancel_url': 'product_list'
    })


# ─────────────────────────────────────────────────────────────
# STOCK IN (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def stock_in_list(request):
    q = request.GET.get('q', '')
    records = StockIn.objects.select_related('product', 'supplier', 'received_by').order_by('-date_received')
    if q:
        records = records.filter(
            Q(product__name__icontains=q) | Q(supplier__name__icontains=q) | Q(invoice_number__icontains=q)
        )
    total_spent = records.aggregate(t=Sum('total_cost'))['t'] or Decimal('0')
    return render(request, 'shop/stock_in/list.html', {
        'records': records, 'q': q, 'total_spent': total_spent
    })


@admin_required
def stock_in_create(request):
    form = StockInForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        stock_in = form.save(commit=False)
        stock_in.received_by = request.user
        stock_in.save()
        
        # Log restock movement
        StockMovement.objects.create(
            product=stock_in.product,
            action_type='RESTOCK',
            quantity_changed=stock_in.quantity,
            unit_cost_at_time=stock_in.buying_price_per_unit,
            selling_price_at_time=stock_in.product.get_selling_price(),
            reference=f"Invoice #{stock_in.invoice_number}" if stock_in.invoice_number else "Supplier Restock",
            user=request.user
        )

        messages.success(request, f'Stock added: {stock_in.quantity} units of {stock_in.product.name}.')
        return redirect('stock_in_list')
    return render(request, 'shop/stock_in/form.html', {'form': form, 'title': 'Record Stock In'})


@admin_required
def stock_in_delete(request, pk):
    record = get_object_or_404(StockIn, pk=pk)
    if request.method == 'POST':
        # Reverse stock update
        product = record.product
        product.current_stock = max(0, product.current_stock - record.quantity)
        product.save()
        record.delete()
        messages.success(request, 'Stock in record deleted and inventory reversed.')
        return redirect('stock_in_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': record, 'obj_name': 'Stock In Record', 'cancel_url': 'stock_in_list'
    })


# ─────────────────────────────────────────────────────────────
# POINT OF SALE (Admin + Attendant)
# ─────────────────────────────────────────────────────────────

@login_required
def pos(request):
    products = Product.objects.filter(is_active=True).select_related('category').order_by('name')
    categories = Category.objects.all()
    # Get cart from session
    cart = request.session.get('cart', {})
    cart_items = []
    cart_total = Decimal('0')
    for prod_id, item_data in cart.items():
        try:
            product = Product.objects.get(pk=int(prod_id))
            subtotal = Decimal(str(item_data['price'])) * item_data['quantity']
            cart_total += subtotal
            cart_items.append({
                'id': prod_id,
                'name': item_data['name'],
                'price': item_data['price'],
                'quantity': item_data['quantity'],
                'subtotal': float(subtotal),
                'max_stock': product.current_stock,
            })
        except Product.DoesNotExist:
            pass
    return render(request, 'shop/sales/pos.html', {
        'products': products,
        'categories': categories,
        'cart_items': cart_items,
        'cart_total': cart_total,
    })


@login_required
def pos_add_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        prod_id = str(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        try:
            product = Product.objects.get(pk=int(prod_id), is_active=True)
            cart = request.session.get('cart', {})
            current_qty = cart.get(prod_id, {}).get('quantity', 0)
            new_qty = current_qty + quantity
            # Removed stock restriction to allow selling items not yet stocked in
            cart[prod_id] = {
                'name': product.name,
                'price': float(product.get_selling_price()),
                'cost': float(product.buying_price),
                'quantity': new_qty,
            }
            request.session['cart'] = cart
            request.session.modified = True
            cart_count = sum(v['quantity'] for v in cart.values())
            cart_total = sum(v['price'] * v['quantity'] for v in cart.values())
            return JsonResponse({'success': True, 'cart_count': cart_count, 'cart_total': cart_total})
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Product not found.'})
    return JsonResponse({'success': False})


@login_required
def pos_remove_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        prod_id = str(data.get('product_id'))
        cart = request.session.get('cart', {})
        if prod_id in cart:
            del cart[prod_id]
            request.session['cart'] = cart
            request.session.modified = True
        cart_total = sum(v['price'] * v['quantity'] for v in cart.values())
        return JsonResponse({'success': True, 'cart_total': cart_total})
    return JsonResponse({'success': False})


@login_required
def pos_update_qty(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        prod_id = str(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        cart = request.session.get('cart', {})
        if prod_id in cart and quantity > 0:
            try:
                product = Product.objects.get(pk=int(prod_id))
                # Removed stock restriction
                cart[prod_id]['quantity'] = quantity
                request.session['cart'] = cart
                request.session.modified = True
            except Product.DoesNotExist:
                pass
        cart_total = sum(v['price'] * v['quantity'] for v in cart.values())
        return JsonResponse({'success': True, 'cart_total': cart_total})
    return JsonResponse({'success': False})


@login_required
def pos_complete_sale(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        notes = data.get('notes', '')
        cart = request.session.get('cart', {})
        if not cart:
            return JsonResponse({'success': False, 'error': 'Cart is empty.'})

        sale = Sale(attendant=request.user, notes=notes)
        sale.save()

        total_amount = Decimal('0')
        total_cost = Decimal('0')

        for prod_id, item_data in cart.items():
            try:
                product = Product.objects.get(pk=int(prod_id))
                qty = item_data['quantity']
                price = Decimal(str(item_data['price']))
                cost = Decimal(str(item_data['cost']))

                # Removed stock restriction

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    product_name=product.name,
                    quantity=qty,
                    unit_price=price,
                    unit_cost=cost,
                )
                # Deduct stock
                product.current_stock -= qty
                product.save()
                
                # Log sale movement
                StockMovement.objects.create(
                    product=product,
                    action_type='SALE',
                    quantity_changed=-qty,
                    unit_cost_at_time=cost,
                    selling_price_at_time=price,
                    reference=f"Sale #{sale.sale_number}",
                    user=request.user
                )

                total_amount += price * qty
                total_cost += cost * qty
            except Product.DoesNotExist:
                pass

        sale.total_amount = total_amount
        sale.total_cost = total_cost
        sale.save()

        # Clear cart
        request.session['cart'] = {}
        request.session.modified = True

        return JsonResponse({
            'success': True,
            'sale_number': sale.sale_number,
            'total': float(total_amount),
            'sale_id': sale.pk,
        })
    return JsonResponse({'success': False})


@login_required
def pos_clear_cart(request):
    request.session['cart'] = {}
    request.session.modified = True
    return JsonResponse({'success': True})


# ─────────────────────────────────────────────────────────────
# SALES
# ─────────────────────────────────────────────────────────────

@login_required
def sale_list(request):
    q = request.GET.get('q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    try:
        is_admin = request.user.profile.is_admin()
    except Exception:
        is_admin = False

    if is_admin:
        sales = Sale.objects.select_related('attendant').prefetch_related('items')
    else:
        sales = Sale.objects.filter(attendant=request.user).prefetch_related('items')

    if q:
        sales = sales.filter(Q(sale_number__icontains=q) | Q(attendant__username__icontains=q))
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)

    sales = sales.order_by('-date')
    totals = sales.aggregate(revenue=Sum('total_amount'), cost=Sum('total_cost'))
    total_revenue = totals['revenue'] or Decimal('0')
    total_cost = totals['cost'] or Decimal('0')

    return render(request, 'shop/sales/list.html', {
        'sales': sales,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'total_revenue': total_revenue,
        'total_profit': total_revenue - total_cost,
        'is_admin': is_admin,
    })


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.select_related('product')
    return render(request, 'shop/sales/detail.html', {'sale': sale, 'items': items})


@admin_required
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST':
        # Restore stock
        for item in sale.items.all():
            if item.product:
                item.product.current_stock += item.quantity
                item.product.save()
                
                # Log adjustment movement due to sale deletion
                StockMovement.objects.create(
                    product=item.product,
                    action_type='ADJUSTMENT',
                    quantity_changed=item.quantity,
                    unit_cost_at_time=item.unit_cost,
                    selling_price_at_time=item.unit_price,
                    reference=f"Reversed Sale #{sale.sale_number}",
                    user=request.user
                )

        sale.delete()
        messages.success(request, 'Sale deleted and stock restored.')
        return redirect('sale_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': sale, 'obj_name': 'Sale', 'cancel_url': 'sale_list'
    })


# ─────────────────────────────────────────────────────────────
# EXPENSES (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def expense_list(request):
    q = request.GET.get('q', '')
    category_f = request.GET.get('category', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    expenses = Expense.objects.select_related('recorded_by').order_by('-date')
    if q:
        expenses = expenses.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category_f:
        expenses = expenses.filter(category=category_f)
    if date_from:
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        expenses = expenses.filter(date__lte=date_to)

    total = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    by_category = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')

    return render(request, 'shop/expenses/list.html', {
        'expenses': expenses,
        'total': total,
        'by_category': by_category,
        'q': q,
        'category_f': category_f,
        'date_from': date_from,
        'date_to': date_to,
        'category_choices': Expense.CATEGORY_CHOICES,
    })


@admin_required
def expense_create(request):
    form = ExpenseForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        expense = form.save(commit=False)
        expense.recorded_by = request.user
        expense.save()
        messages.success(request, 'Expense recorded.')
        return redirect('expense_list')
    return render(request, 'shop/expenses/form.html', {'form': form, 'title': 'Record Expense'})


@admin_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=expense)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Expense updated.')
        return redirect('expense_list')
    return render(request, 'shop/expenses/form.html', {'form': form, 'title': 'Edit Expense', 'obj': expense})


@admin_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
        return redirect('expense_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': expense, 'obj_name': 'Expense', 'cancel_url': 'expense_list'
    })


# ─────────────────────────────────────────────────────────────
# STOCK ADJUSTMENTS / LOSSES (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def adjustment_list(request):
    adjustments = StockAdjustment.objects.select_related('product', 'recorded_by').order_by('-date')
    total_loss_value = adjustments.filter(adjustment_type='loss').aggregate(
        t=Sum('estimated_value')
    )['t'] or Decimal('0')
    return render(request, 'shop/adjustments/list.html', {
        'adjustments': adjustments,
        'total_loss_value': total_loss_value,
    })


@admin_required
def adjustment_create(request):
    form = StockAdjustmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        adj = form.save(commit=False)
        adj.recorded_by = request.user
        adj.save()
        
        StockMovement.objects.create(
            product=adj.product,
            action_type='ADJUSTMENT',
            quantity_changed=adj.quantity if adj.adjustment_type == 'gain' else -adj.quantity,
            unit_cost_at_time=adj.product.buying_price,
            selling_price_at_time=adj.product.get_selling_price(),
            reference=f"Adjustment: {adj.get_reason_display()}",
            user=request.user
        )

        messages.success(request, f'Stock adjustment recorded for {adj.product.name}.')
        return redirect('adjustment_list')
    return render(request, 'shop/adjustments/form.html', {'form': form, 'title': 'Record Stock Adjustment'})


# ─────────────────────────────────────────────────────────────
# REPORTS (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def stock_history(request):
    movements = StockMovement.objects.select_related('product', 'user').order_by('-date')
    product_filter = request.GET.get('product', '')
    if product_filter:
        movements = movements.filter(product_id=product_filter)
    products = Product.objects.all().order_by('name')
    return render(request, 'shop/reports/stock_history.html', {
        'movements': movements,
        'products': products,
        'product_filter': product_filter
    })


@admin_required
def price_history(request):
    history = PriceHistory.objects.select_related('product', 'user').order_by('-date')
    product_filter = request.GET.get('product', '')
    if product_filter:
        history = history.filter(product_id=product_filter)
    products = Product.objects.all().order_by('name')
    return render(request, 'shop/reports/price_history.html', {
        'history': history,
        'products': products,
        'product_filter': product_filter
    })


@admin_required
def stock_report(request):
    products = Product.objects.filter(is_active=True).select_related('category').order_by('name')
    category_filter = request.GET.get('category', '')
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    total_value = sum(p.stock_value() for p in products)
    total_potential = sum(p.potential_revenue() for p in products)
    
    categories = Category.objects.all()
    return render(request, 'shop/reports/stock_report.html', {
        'products': products,
        'categories': categories,
        'category_filter': category_filter,
        'total_value': total_value,
        'total_potential': total_potential
    })


@login_required
def reports(request):
    """Role-aware reports. Admins see full P&L. Attendants see only their own sales, no profit data."""
    period = request.GET.get('period', 'monthly')
    today = timezone.now().date()
    date_from_custom = request.GET.get('date_from', '')
    date_to_custom = request.GET.get('date_to', '')

    try:
        is_admin = request.user.profile.is_admin()
    except Exception:
        is_admin = False

    if period == 'today':
        start = today
        end = today
        label = "Today"
    elif period == 'week':
        start = today - timedelta(days=7)
        end = today
        label = "Last 7 Days"
    elif period == 'monthly':
        start = today.replace(day=1)
        end = today
        label = f"This Month ({today.strftime('%B %Y')})"
    elif period == 'yearly':
        start = today.replace(month=1, day=1)
        end = today
        label = f"This Year ({today.year})"
    elif period == 'custom' and date_from_custom and date_to_custom:
        from datetime import datetime
        start = datetime.strptime(date_from_custom, '%Y-%m-%d').date()
        end = datetime.strptime(date_to_custom, '%Y-%m-%d').date()
        label = f"Custom: {start.strftime('%d %b %Y')} — {end.strftime('%d %b %Y')}"
    else:
        start = today.replace(day=1)
        end = today
        label = "This Month"

    # ---- ADMIN FULL REPORT ----
    if is_admin:
        sales = Sale.objects.filter(date__date__gte=start, date__date__lte=end)
        revenue = sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
        cogs = sales.aggregate(t=Sum('total_cost'))['t'] or Decimal('0')
        gross_profit = revenue - cogs

        expenses = Expense.objects.filter(date__gte=start, date__lte=end)
        total_exp = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        net_profit = gross_profit - total_exp

        losses = StockAdjustment.objects.filter(
            adjustment_type='loss', date__date__gte=start, date__date__lte=end
        )
        total_losses = losses.aggregate(t=Sum('estimated_value'))['t'] or Decimal('0')

        top_products = SaleItem.objects.filter(
            sale__date__date__gte=start, sale__date__date__lte=end
        ).values('product__name').annotate(
            qty=Sum('quantity'), revenue=Sum('total')
        ).order_by('-revenue')[:10]

        attendant_performance = Sale.objects.filter(
            date__date__gte=start, date__date__lte=end
        ).values('attendant__username', 'attendant__first_name', 'attendant__last_name').annotate(
            sales_count=Count('id'), revenue=Sum('total_amount')
        ).order_by('-revenue')

        expense_by_cat = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')

        daily_trend = []
        current = start
        while current <= end:
            day_sales = Sale.objects.filter(date__date=current)
            day_rev = day_sales.aggregate(t=Sum('total_amount'))['t'] or 0
            day_exp = Expense.objects.filter(date=current).aggregate(t=Sum('amount'))['t'] or 0
            daily_trend.append({
                'date': current.strftime('%d %b'),
                'revenue': float(day_rev),
                'expenses': float(day_exp),
            })
            current += timedelta(days=1)

        context = {
            'is_admin': True,
            'period': period,
            'label': label,
            'start': start,
            'end': end,
            'revenue': revenue,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'total_exp': total_exp,
            'net_profit': net_profit,
            'total_losses': total_losses,
            'sales_count': sales.count(),
            'top_products': top_products,
            'attendant_performance': attendant_performance,
            'expense_by_cat': expense_by_cat,
            'daily_trend': json.dumps(daily_trend),
            'date_from_custom': date_from_custom,
            'date_to_custom': date_to_custom,
        }
    else:
        # ---- ATTENDANT RESTRICTED REPORT (own sales only, NO profit) ----
        my_sales = Sale.objects.filter(
            attendant=request.user,
            date__date__gte=start,
            date__date__lte=end
        )
        my_revenue = my_sales.aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
        my_items = SaleItem.objects.filter(
            sale__attendant=request.user,
            sale__date__date__gte=start,
            sale__date__date__lte=end
        )
        my_top_products = my_items.values('product__name').annotate(
            qty=Sum('quantity'), revenue=Sum('total')
        ).order_by('-revenue')[:10]

        daily_trend = []
        current = start
        while current <= end:
            day_rev = Sale.objects.filter(
                attendant=request.user, date__date=current
            ).aggregate(t=Sum('total_amount'))['t'] or 0
            daily_trend.append({
                'date': current.strftime('%d %b'),
                'revenue': float(day_rev),
                'expenses': 0,  # attendant does not see expenses
            })
            current += timedelta(days=1)

        context = {
            'is_admin': False,
            'period': period,
            'label': label,
            'start': start,
            'end': end,
            'revenue': my_revenue,
            'sales_count': my_sales.count(),
            'top_products': my_top_products,
            'daily_trend': json.dumps(daily_trend),
            'date_from_custom': date_from_custom,
            'date_to_custom': date_to_custom,
        }

    return render(request, 'shop/reports/reports.html', context)


@admin_required
def print_stickers(request):
    """Printable price sticker sheet for admin."""
    category_id = request.GET.get('category', '')
    products = Product.objects.filter(is_active=True).select_related('category')
    if category_id:
        products = products.filter(category_id=category_id)
    categories = Category.objects.all()
    return render(request, 'shop/products/stickers.html', {
        'products': products,
        'categories': categories,
        'category_id': category_id,
    })


# ─────────────────────────────────────────────────────────────
# USER MANAGEMENT (Admin only)
# ─────────────────────────────────────────────────────────────

@admin_required
def user_list(request):
    users = User.objects.select_related('profile').filter(is_active=True).order_by('username')
    return render(request, 'shop/users/list.html', {'users': users})


@admin_required
def user_create(request):
    form = AttendantCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        user.save()
        UserProfile.objects.create(
            user=user,
            role=form.cleaned_data['role'],
            phone=form.cleaned_data.get('phone', ''),
        )
        messages.success(request, f'User {user.username} created successfully.')
        return redirect('user_list')
    return render(request, 'shop/users/form.html', {'form': form, 'title': 'Add User'})


@admin_required
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile(user=user)

    initial = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'phone': profile.phone,
        'role': profile.role,
    }
    form = AttendantUpdateForm(request.POST or None, instance=user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        user.save()
        profile.phone = form.cleaned_data.get('phone', '')
        profile.role = form.cleaned_data.get('role', 'ATTENDANT')
        profile.save()
        messages.success(request, 'User updated.')
        return redirect('user_list')
    return render(request, 'shop/users/form.html', {'form': form, 'title': 'Edit User', 'obj': user})


@admin_required
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')
    if request.method == 'POST':
        user.is_active = False
        user.save()
        messages.success(request, 'User deactivated.')
        return redirect('user_list')
    return render(request, 'shop/confirm_delete.html', {
        'obj': user, 'obj_name': 'User', 'cancel_url': 'user_list'
    })


# ─────────────────────────────────────────────────────────────
# AJAX HELPERS
# ─────────────────────────────────────────────────────────────

@login_required
def get_product_info(request, pk):
    try:
        product = Product.objects.get(pk=pk, is_active=True)
        return JsonResponse({
            'id': product.pk,
            'name': product.name,
            'brand': product.brand,
            'model_number': product.model_number,
            'description': product.description,
            'selling_price': float(product.get_selling_price()),
            'buying_price': float(product.buying_price),
            'current_stock': product.current_stock,
            'unit': product.unit,
            'barcode': product.barcode or '',
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
def search_products(request):
    q = request.GET.get('q', '')
    products = Product.objects.filter(
        is_active=True
    )
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(brand__icontains=q) | Q(barcode__icontains=q)
        )
    data = [{
        'id': p.pk,
        'name': p.name,
        'brand': p.brand,
        'price': float(p.get_selling_price()),
        'stock': p.available_stock(),
        'unit': p.unit,
    } for p in products[:20]]
    return JsonResponse({'products': data})


# ─────────────────────────────────────────────────────────────
# ONLINE STORE ADMIN VIEWS
# ─────────────────────────────────────────────────────────────

@admin_required
def store_settings(request):
    settings, created = StoreSettings.objects.get_or_create(id=1)
    form = StoreSettingsForm(request.POST or None, instance=settings)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Store payment settings updated.')
        return redirect('store_settings')
    return render(request, 'shop/store/settings.html', {'form': form, 'title': 'Store Settings'})


@login_required
def admin_online_orders(request):
    orders = OnlineOrder.objects.all().order_by('-created_at')
    
    # Allow filtering
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
        
    return render(request, 'shop/store/admin_orders.html', {
        'orders': orders,
        'status_filter': status_filter
    })


@login_required
def admin_order_complete(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk)
    if request.method == 'POST' and order.status not in ['COMPLETED', 'CANCELLED']:
        # Create a Sale for this order
        sale = Sale.objects.create(
            attendant=request.user,
            notes=f"Online Order #{order.order_number} by {order.customer_name}"
        )
        total_amount = Decimal('0')
        total_cost = Decimal('0')

        for item in order.items.all():
            product = item.product
            qty = item.quantity
            price = item.unit_price
            cost = product.buying_price if product else Decimal('0')
            
            SaleItem.objects.create(
                sale=sale,
                product=product,
                product_name=item.product_name,
                quantity=qty,
                unit_price=price,
                unit_cost=cost
            )
            total_amount += price * qty
            total_cost += cost * qty
            
            if product:
                # Deduct from actual stock and reserved stock
                product.current_stock = max(0, product.current_stock - qty)
                product.reserved_stock = max(0, product.reserved_stock - qty)
                product.save()
                
                StockMovement.objects.create(
                    product=product,
                    action_type='ONLINE_ORDER',
                    quantity_changed=-qty,
                    unit_cost_at_time=cost,
                    selling_price_at_time=price,
                    reference=f"Online Order #{order.order_number}",
                    user=request.user
                )

        sale.total_amount = total_amount
        sale.total_cost = total_cost
        sale.save()
        
        order.status = 'COMPLETED'
        order.save()
        messages.success(request, f'Order {order.order_number} marked as completed and sale recorded.')
        
    return redirect('admin_online_orders')


@login_required
def admin_order_cancel(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk)
    if request.method == 'POST' and order.status not in ['COMPLETED', 'CANCELLED']:
        # Free up reserved stock
        for item in order.items.all():
            if item.product:
                item.product.reserved_stock = max(0, item.product.reserved_stock - item.quantity)
                item.product.save()
        
        order.status = 'CANCELLED'
        order.save()
        messages.success(request, f'Order {order.order_number} cancelled and stock reservation removed.')
        
    return redirect('admin_online_orders')


@login_required
def admin_order_update_status(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk)
    if request.method == 'POST' and order.status not in ['COMPLETED', 'CANCELLED']:
        new_status = request.POST.get('new_status')
        if new_status in ['READY_FOR_PICKUP', 'OUT_FOR_DELIVERY']:
            order.status = new_status
            order.save()
            messages.success(request, f'Order {order.order_number} status updated to {order.get_status_display()}.')
    return redirect('admin_online_orders')


# ─────────────────────────────────────────────────────────────
# PUBLIC STOREFRONT VIEWS
# ─────────────────────────────────────────────────────────────

def store_home(request):
    query = request.GET.get('q', '').strip()
    cat_id = request.GET.get('category', '')
    
    # Only show active products and optimize query
    products = Product.objects.select_related('category').filter(is_active=True)
    
    if query:
        # Related keyword lookup dictionary for enhanced search
        related_keywords = {
            'phone': ['phone', 'smartphone', 'mobile', 'cell', 'iphone', 'samsung', 'tecno', 'infinix', 'itel'],
            'charger': ['charger', 'adapter', 'charging', 'fast', 'usb', 'cable', 'type-c', 'power'],
            'cable': ['cable', 'wire', 'cord', 'usb', 'type-c', 'lightning', 'fast'],
            'audio': ['earphone', 'headphone', 'headset', 'audio', 'airpods', 'buds', 'speaker', 'sound'],
            'case': ['case', 'cover', 'pouch', 'protector', 'guard'],
        }
        
        words = [w for w in query.split() if len(w) > 0]
        query_filter = Q()
        
        for word in words:
            word_lower = word.lower()
            term_filter = (
                Q(name__icontains=word) |
                Q(brand__icontains=word) |
                Q(description__icontains=word) |
                Q(model_number__icontains=word) |
                Q(category__name__icontains=word) |
                Q(barcode__icontains=word)
            )
            # Check for synonyms and related terms
            for key, term_list in related_keywords.items():
                if word_lower in key or key in word_lower:
                    for rel_term in term_list:
                        term_filter |= (
                            Q(name__icontains=rel_term) |
                            Q(brand__icontains=rel_term) |
                            Q(description__icontains=rel_term) |
                            Q(category__name__icontains=rel_term)
                        )
            
            query_filter &= term_filter

        products = products.filter(query_filter).distinct()

    if cat_id:
        products = products.filter(category_id=cat_id)

    products = products.order_by('name')
        
    categories = Category.objects.all()
    
    cart = request.session.get('store_cart', {})
    cart_count = sum(item['qty'] for item in cart.values())
    
    # Get one random featured product for popup ad
    featured_ad = Product.objects.filter(is_active=True, is_featured=True).order_by('?').first()
    
    return render(request, 'shop/store/home.html', {
        'products': products,
        'categories': categories,
        'q': query,
        'cat_id': cat_id,
        'cart_count': cart_count,
        'featured_ad': featured_ad,
    })


def store_product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk, is_active=True)
    
    host = request.get_host()
    scheme = 'https' if request.is_secure() or 'twiina.com' in host else request.scheme
    domain = 'shop.twiina.com' if 'twiina.com' in host else (host if ':' in host else f"{host}:8001")
    
    share_url = f"{scheme}://{domain}/product/{product.pk}/"

    if product.image:
        image_url = product.image.url
        if image_url.startswith('http://') or image_url.startswith('https://'):
            absolute_image_url = image_url
        else:
            absolute_image_url = f"{scheme}://{domain}{image_url}"
    else:
        absolute_image_url = f"{scheme}://{domain}/static/images/twiina_logo.png"


    # Related products from same category or brand
    related_products = Product.objects.select_related('category').filter(
        Q(category=product.category) | Q(brand=product.brand),
        is_active=True
    ).exclude(pk=product.pk)[:4]
    cart = request.session.get('store_cart', {})
    cart_count = sum(item['qty'] for item in cart.values())

    return render(request, 'shop/store/product_detail.html', {
        'product': product,
        'related_products': related_products,
        'share_url': share_url,
        'absolute_image_url': absolute_image_url,
        'cart_count': cart_count,
    })



def store_cart_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        action = data.get('action')
        prod_id = str(data.get('product_id'))
        
        cart = request.session.get('store_cart', {})
        
        if action == 'add':
            qty = int(data.get('quantity', 1))
            try:
                product = Product.objects.get(pk=int(prod_id), is_active=True)
                available = product.available_stock()
                current_qty = cart.get(prod_id, {}).get('qty', 0)
                
                if current_qty + qty > available:
                    return JsonResponse({'success': False, 'error': f'Only {available} available in stock.'})
                    
                cart[prod_id] = {
                    'name': product.name,
                    'price': float(product.get_effective_price()),
                    'image_url': product.image.url if product.image else '',
                    'qty': current_qty + qty
                }
            except Product.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Product not found.'})
                
        elif action == 'remove':
            if prod_id in cart:
                del cart[prod_id]
                
        elif action == 'update':
            qty = int(data.get('quantity', 1))
            if prod_id in cart:
                try:
                    product = Product.objects.get(pk=int(prod_id))
                    available = product.available_stock()
                    if qty > available:
                        return JsonResponse({'success': False, 'error': f'Only {available} available.'})
                    if qty <= 0:
                        del cart[prod_id]
                    else:
                        cart[prod_id]['qty'] = qty
                except Product.DoesNotExist:
                    pass

        request.session['store_cart'] = cart
        request.session.modified = True
        
        cart_count = sum(item['qty'] for item in cart.values())
        cart_total = sum(item['price'] * item['qty'] for item in cart.values())
        
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'cart_total': cart_total,
            'cart': cart
        })
    return JsonResponse({'success': False})


def store_cart(request):
    cart = request.session.get('store_cart', {})
    cart_items = []
    cart_total = 0
    
    # Fetch products to augment cart data
    product_ids = [int(pid) for pid in cart.keys() if pid.isdigit()]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
    
    for pid, item in cart.items():
        subtotal = item['price'] * item['qty']
        cart_total += subtotal
        
        p = products.get(int(pid))
        
        cart_items.append({
            'id': pid,
            'name': item['name'],
            'price': item['price'],
            'qty': item['qty'],
            'image_url': item.get('image_url', ''),
            'subtotal': subtotal,
            'original_price': float(p.get_selling_price()) if p else None,
            'source_type': p.source_type if p else '',
            'delivery_days': p.estimated_delivery_days if p else 1,
            'brand': p.brand if p else '',
        })
        
    return render(request, 'shop/store/cart.html', {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'cart_count': sum(item['qty'] for item in cart.values())
    })


def store_checkout(request):
    cart = request.session.get('store_cart', {})
    if not cart:
        return redirect('store_home')
        
    cart_total = sum(Decimal(str(item['price'])) * item['qty'] for item in cart.values())
    settings, _ = StoreSettings.objects.get_or_create(id=1)
    from .models import DeliveryRegion
    regions = DeliveryRegion.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        payment_method = request.POST.get('payment_method')
        region_id = request.POST.get('region_id')
        
        region = None
        delivery_fee = Decimal('0.00')
        if region_id:
            if region_id == 'call':
                pass # Fee remains 0, user will call
            elif str(region_id).isdigit():
                try:
                    region = DeliveryRegion.objects.get(pk=region_id, is_active=True)
                    delivery_fee = region.fee
                except DeliveryRegion.DoesNotExist:
                    pass
        
        # Verify stock again
        for pid, item in cart.items():
            try:
                product = Product.objects.get(pk=int(pid))
                if item['qty'] > product.available_stock():
                    messages.error(request, f"Sorry, {product.name} only has {product.available_stock()} available.")
                    return redirect('store_cart')
            except Product.DoesNotExist:
                messages.error(request, f"A product in your cart is no longer available.")
                return redirect('store_cart')
                
        # Create Order
        order = OnlineOrder.objects.create(
            customer_name=name,
            customer_phone=phone,
            customer_address=address,
            delivery_region=region,
            delivery_fee=delivery_fee,
            payment_method=payment_method,
            total_amount=cart_total + delivery_fee
        )
        
        # Create Items and reserve stock
        for pid, item in cart.items():
            product = Product.objects.get(pk=int(pid))
            OnlineOrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=item['qty'],
                unit_price=Decimal(str(item['price']))
            )
            # Reserve stock immediately
            product.reserved_stock += item['qty']
            product.save()
            
        # Clear cart
        request.session['store_cart'] = {}
        request.session.modified = True
        
        return render(request, 'shop/store/success.html', {'order': order, 'settings': settings})
        
    return render(request, 'shop/store/checkout.html', {
        'cart_total': cart_total,
        'settings': settings,
        'regions': regions,
        'cart_count': sum(item['qty'] for item in cart.values())
    })


# ─────────────────────────────────────────────────────────────
# PDF CATALOG
# ─────────────────────────────────────────────────────────────

def download_catalog_pdf(request):
    """Generate and download a product catalog PDF."""
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    category_id = request.GET.get('category', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    products = Product.objects.filter(is_active=True).select_related('category').order_by('category__name', 'name')

    filter_parts = []
    if category_id and category_id.isdigit():
        products = products.filter(category_id=category_id)
        try:
            cat = Category.objects.get(pk=category_id)
            filter_parts.append(f"Category: {cat.name}")
        except Category.DoesNotExist:
            pass

    if start_date:
        try:
            from datetime import datetime
            sd = datetime.strptime(start_date, '%Y-%m-%d').date()
            products = products.filter(date_added__date__gte=sd)
            filter_parts.append(f"From: {start_date}")
        except Exception:
            pass

    if end_date:
        try:
            from datetime import datetime
            ed = datetime.strptime(end_date, '%Y-%m-%d').date()
            products = products.filter(date_added__date__lte=ed)
            filter_parts.append(f"To: {end_date}")
        except Exception:
            pass

    context = {
        'products': products,
        'filter_label': ' | '.join(filter_parts) if filter_parts else None,
        'generated_at': timezone.now().strftime('%d %b %Y, %I:%M %p'),
        'categories': Category.objects.all().order_by('name'),
    }

    html_string = render_to_string('shop/store/catalog_pdf.html', context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_string.encode('utf-8')), result)

    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="twiina_catalog.pdf"'
        return response
    else:
        return HttpResponse('Error generating PDF', status=500)
