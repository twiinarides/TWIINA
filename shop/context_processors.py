from .models import Product, Sale
from django.utils import timezone


def global_context(request):
    if request.user.is_authenticated:
        low_stock_count = Product.objects.filter(
            current_stock__lte=models_min_stock(), is_active=True
        ).count()
        today_sales = Sale.objects.filter(
            date__date=timezone.now().date()
        ).count()
        try:
            user_role = request.user.profile.role
        except Exception:
            user_role = 'ATTENDANT'
        return {
            'low_stock_count': low_stock_count,
            'today_sales_count': today_sales,
            'user_role': user_role,
        }
    return {}


def models_min_stock():
    # Helper to avoid circular import - just use a direct query
    from django.db.models import F
    return F('minimum_stock')
