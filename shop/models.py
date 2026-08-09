from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import json
from decimal import Decimal


class UserProfile(models.Model):
    ROLE_CHOICES = [('ADMIN', 'Admin'), ('ATTENDANT', 'Attendant')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ATTENDANT')
    phone = models.CharField(max_length=20, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_admin(self):
        return self.role == 'ADMIN'

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Bootstrap icon name e.g. bi-phone")
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def product_count(self):
        return self.product_set.filter(is_active=True).count()

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def total_purchases_amount(self):
        return self.stockin_set.aggregate(
            total=models.Sum('total_cost')
        )['total'] or Decimal('0.00')

    def total_orders(self):
        return self.stockin_set.count()

    def __str__(self):
        return self.name


class ProductTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=30, default='primary',
                             help_text="Bootstrap color: primary, success, danger, warning, info, dark")

    def __str__(self):
        return self.name


class Product(models.Model):
    PRICING_MODE_CHOICES = [
        ('MARKUP', 'Markup Percentage'),
        ('DIRECT', 'Direct Selling Price'),
    ]
    UNIT_CHOICES = [
        ('piece', 'Piece'), ('pair', 'Pair'), ('box', 'Box'),
        ('set', 'Set'), ('dozen', 'Dozen'), ('unit', 'Unit'),
        ('roll', 'Roll'), ('metre', 'Metre'), ('kit', 'Kit'),
    ]
    CONDITION_CHOICES = [
        ('NEW', 'Brand New'),
        ('USED', 'Used'),
        ('REFURBISHED', 'Refurbished'),
    ]
    SOURCE_CHOICES = [
        ('DIRECT', 'In Shop (Direct Stock)'),
        ('WAREHOUSE', 'Warehouse Stock'),
        ('SUPPLIER', 'Order from Supplier'),
    ]

    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='piece')
    image = models.ImageField(upload_to='products/', blank=True, null=True)

    # Product enrichment
    condition = models.CharField(max_length=15, choices=CONDITION_CHOICES, default='NEW')
    source_type = models.CharField(max_length=15, choices=SOURCE_CHOICES, default='DIRECT')
    warehouse_location = models.CharField(max_length=200, blank=True, help_text="e.g. Kisekka Market, Kampala")
    estimated_delivery_days = models.PositiveSmallIntegerField(default=1,
                                                               help_text="Estimated delivery days for this item")
    specifications = models.TextField(blank=True,
                                      help_text="JSON: [{\"key\": \"RAM\", \"value\": \"8GB\"}, ...]")
    tags = models.ManyToManyField(ProductTag, blank=True)
    is_featured = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)

    # Pricing
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pricing_mode = models.CharField(max_length=10, choices=PRICING_MODE_CHOICES, default='MARKUP')
    markup_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('50.00'))
    direct_selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Flash Sale
    flash_sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                           help_text="Discounted flash sale price (leave blank for no sale)")
    flash_sale_ends = models.DateTimeField(null=True, blank=True,
                                           help_text="When the flash sale expires")

    # Stock
    current_stock = models.PositiveIntegerField(default=0)
    reserved_stock = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(default=5)

    is_active = models.BooleanField(default=True)
    date_added = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def get_selling_price(self):
        if self.pricing_mode == 'MARKUP':
            return self.buying_price * (1 + self.markup_percentage / Decimal('100'))
        return self.direct_selling_price or self.buying_price

    def get_effective_price(self):
        """Return flash sale price if active, else regular selling price."""
        if self.flash_sale_price and self.flash_sale_ends and self.flash_sale_ends > timezone.now():
            return self.flash_sale_price
        return self.get_selling_price()

    def is_on_flash_sale(self):
        return bool(
            self.flash_sale_price and
            self.flash_sale_ends and
            self.flash_sale_ends > timezone.now()
        )

    def get_discount_percentage(self):
        if self.is_on_flash_sale():
            original = self.get_selling_price()
            if original > 0:
                return int(((original - self.flash_sale_price) / original) * 100)
        return 0

    def get_specifications(self):
        """Parse specifications JSON safely."""
        if not self.specifications:
            return []
        try:
            data = json.loads(self.specifications)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def get_profit_per_unit(self):
        return self.get_selling_price() - self.buying_price

    def get_margin_percentage(self):
        sp = self.get_selling_price()
        if sp > 0:
            return ((sp - self.buying_price) / sp) * 100
        return Decimal('0')

    def is_low_stock(self):
        return self.available_stock() <= self.minimum_stock

    def available_stock(self):
        return max(0, self.current_stock - self.reserved_stock)

    def stock_value(self):
        return self.current_stock * self.buying_price

    def potential_revenue(self):
        return self.current_stock * self.get_selling_price()

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    """Additional product images for gallery."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/gallery/')
    sort_order = models.PositiveSmallIntegerField(default=0)
    alt_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.product.name} — image {self.sort_order}"


class StockIn(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_ins')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='stockin_set')
    quantity = models.PositiveIntegerField()
    buying_price_per_unit = models.DecimalField(max_digits=12, decimal_places=2)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    invoice_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_ins')
    date_received = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stock In"
        verbose_name_plural = "Stock In Records"
        ordering = ['-date_received']

    def save(self, *args, **kwargs):
        self.total_cost = Decimal(str(self.quantity)) * self.buying_price_per_unit
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            product = self.product
            product.current_stock += self.quantity
            product.buying_price = self.buying_price_per_unit
            product.save()

    def __str__(self):
        return f"{self.product.name} x{self.quantity} on {self.date_received.strftime('%Y-%m-%d')}"


class Sale(models.Model):
    sale_number = models.CharField(max_length=20, unique=True, editable=False)
    attendant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sales')
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if not self.sale_number:
            self.sale_number = f"TW{timezone.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
        super().save(*args, **kwargs)

    @property
    def gross_profit(self):
        return self.total_amount - self.total_cost

    @property
    def item_count(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0

    def __str__(self):
        return f"Sale #{self.sale_number}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='sale_items')
    product_name = models.CharField(max_length=200, default='')
    product_brand = models.CharField(max_length=100, blank=True, default='')
    product_model = models.CharField(max_length=100, blank=True, default='')
    product_description = models.TextField(blank=True, default='')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total = Decimal(str(self.quantity)) * self.unit_price
        if self.product:
            if not self.product_name:
                self.product_name = self.product.name
            if not self.product_brand:
                self.product_brand = self.product.brand
            if not self.product_model:
                self.product_model = self.product.model_number
            if not self.product_description:
                self.product_description = self.product.description
        super().save(*args, **kwargs)

    @property
    def profit(self):
        return (self.unit_price - self.unit_cost) * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('rent', 'Rent'), ('electricity', 'Electricity/Utilities'),
        ('salary', 'Salary/Wages'), ('transport', 'Transport'),
        ('maintenance', 'Maintenance/Repairs'), ('marketing', 'Marketing/Advertising'),
        ('supplies', 'Office Supplies'), ('insurance', 'Insurance'),
        ('tax', 'Tax/Licenses'), ('other', 'Other'),
    ]
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='expenses')
    receipt_image = models.ImageField(upload_to='receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.title} - UGX {self.amount}"


class StockAdjustment(models.Model):
    REASON_CHOICES = [
        ('damage', 'Damaged/Defective'), ('theft', 'Theft/Missing'),
        ('expired', 'Expired/Obsolete'), ('correction', 'Stock Count Correction'),
        ('return_in', 'Customer Return (add back)'), ('other', 'Other'),
    ]
    TYPE_CHOICES = [
        ('loss', 'Loss (subtract from stock)'),
        ('gain', 'Gain (add to stock)'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='adjustments')

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            self.estimated_value = self.quantity * self.product.buying_price
        super().save(*args, **kwargs)
        if is_new:
            product = self.product
            if self.adjustment_type == 'loss':
                product.current_stock = max(0, product.current_stock - self.quantity)
            else:
                product.current_stock += self.quantity
            product.save()

    def __str__(self):
        return f"{self.product.name} - {self.adjustment_type} of {self.quantity}"


# ─────────────────────────────────────────────────────────────
# ONLINE STORE MODELS
# ─────────────────────────────────────────────────────────────

class StoreSettings(models.Model):
    mtn_merchant_number = models.CharField(max_length=20, blank=True, help_text="e.g. 077XXXXXXX")
    airtel_merchant_number = models.CharField(max_length=20, blank=True, help_text="e.g. 075XXXXXXX")

    # Delivery fee settings
    delivery_fee_kampala = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5000'),
                                               help_text="Delivery fee within Kampala (UGX)")
    delivery_fee_upcountry = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('15000'),
                                                  help_text="Delivery fee upcountry/outside Kampala (UGX)")
    free_delivery_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('200000'),
                                                   help_text="Order amount above which delivery is FREE (UGX)")
    free_delivery_enabled = models.BooleanField(default=True,
                                                help_text="Enable free delivery above the threshold?")

    # Store info
    store_tagline = models.CharField(max_length=200, blank=True, default="Best Tech Deals in Uganda")
    hero_banner_text = models.CharField(max_length=300, blank=True,
                                        default="Quality Electronics & Gadgets — Fast Delivery Across Uganda")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Store Settings"

    def __str__(self):
        return "Store Settings"


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2,
                                              help_text="Percentage discount e.g. 10 = 10%")
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'),
                                           help_text="Minimum order to qualify")
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self, order_amount=Decimal('0')):
        if not self.is_active:
            return False, "This promo code is inactive."
        if self.expires_at and self.expires_at < timezone.now():
            return False, "This promo code has expired."
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False, "This promo code has reached its usage limit."
        if order_amount < self.min_order_amount:
            return False, f"Minimum order of UGX {self.min_order_amount:,.0f} required."
        return True, "Valid"

    def __str__(self):
        return f"{self.code} — {self.discount_percentage}% off"


class OnlineOrder(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('READY_FOR_PICKUP', 'Ready for Pickup'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    PAYMENT_CHOICES = [
        ('MERCHANT', 'Pay by Merchant (MTN/Airtel)'),
        ('DELIVERY', 'Cash on Delivery'),
    ]
    DELIVERY_ZONE_CHOICES = [
        ('kampala', 'Kampala & Environs'),
        ('upcountry', 'Upcountry / Outside Kampala'),
    ]

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_address = models.TextField()
    delivery_zone = models.CharField(max_length=20, choices=DELIVERY_ZONE_CHOICES, default='kampala')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='DELIVERY')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promo_code = models.CharField(max_length=50, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD{timezone.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.order_number} by {self.customer_name}"


class OnlineOrderItem(models.Model):
    order = models.ForeignKey(OnlineOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='online_order_items')
    product_name = models.CharField(max_length=200, default='')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total = Decimal(str(self.quantity)) * self.unit_price
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# HISTORY & AUDIT MODELS
# ─────────────────────────────────────────────────────────────

class StockMovement(models.Model):
    ACTION_CHOICES = [
        ('INITIAL_STOCK', 'Initial Stock'),
        ('RESTOCK', 'Stock In (Supplier)'),
        ('SALE', 'POS Sale'),
        ('ADJUSTMENT', 'Manual Adjustment'),
        ('ONLINE_ORDER', 'Online Order Sale'),
        ('CANCELLED_ORDER', 'Online Order Cancelled'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_movements')
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_changed = models.IntegerField(help_text="Positive for additions, negative for deductions")
    unit_cost_at_time = models.DecimalField(max_digits=12, decimal_places=2,
                                            help_text="Buying price at the time of movement")
    selling_price_at_time = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                help_text="Selling price at the time of movement")
    reference = models.CharField(max_length=200, blank=True,
                                 help_text="e.g. Sale #TW123 or Invoice #INV456")
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.product.name} {self.action_type} ({self.quantity_changed}) on {self.date.strftime('%Y-%m-%d')}"


class PriceHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_history')
    old_buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    old_selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.product.name} price changed on {self.date.strftime('%Y-%m-%d')}"
