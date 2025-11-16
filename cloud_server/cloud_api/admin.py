from django.contrib import admin
from .models import (
    User, Role, Restaurant, UserRole, RestaurantTable, LocalServer, Menu, MenuItem,
    InventoryItem, MenuItemIngredient, Supplier, RestaurantSupplier, DeliveryBatch,
    KitchenDisplayOrder, Order, SalesOrder, OrderItem, Booking, OrderItemRejection,
    SupplyOrder, DeliveryPartner, DeliveryTracking, BillingRecord, Transaction,
    CustomerAccount, PaymentMethod, StaffShift, StaffShiftAssignment,
    TableAssignment, StaffPerformanceHistory, CommunicationGroup
)

admin.site.register(User)
admin.site.register(Role)
admin.site.register(Restaurant)
admin.site.register(UserRole)
admin.site.register(RestaurantTable)
admin.site.register(LocalServer)
admin.site.register(Menu)
admin.site.register(MenuItem)
admin.site.register(InventoryItem)
admin.site.register(MenuItemIngredient)
admin.site.register(Supplier)
admin.site.register(RestaurantSupplier)
admin.site.register(DeliveryBatch)
admin.site.register(KitchenDisplayOrder)
admin.site.register(Order)
admin.site.register(SalesOrder)
admin.site.register(OrderItem)
admin.site.register(Booking)
admin.site.register(OrderItemRejection)
admin.site.register(SupplyOrder)
admin.site.register(DeliveryPartner)
admin.site.register(DeliveryTracking)
admin.site.register(BillingRecord)
admin.site.register(Transaction)
admin.site.register(CustomerAccount)
admin.site.register(PaymentMethod)

admin.site.register(StaffShift)
admin.site.register(StaffShiftAssignment)
admin.site.register(TableAssignment)
admin.site.register(StaffPerformanceHistory)
admin.site.register(CommunicationGroup)
