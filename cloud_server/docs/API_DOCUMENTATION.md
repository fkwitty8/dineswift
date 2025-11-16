# Menu Management API Documentation

## Add Menu Item

**Endpoint:** `POST /api/menu/items/add/`

**Description:** Allows restaurant managers to add new menu items to their restaurant's menu.

### Authentication
- Requires authentication token
- User must have 'manager' role
- Manager can only add items to their own restaurant's menu

### Request Headers
```
Content-Type: application/json
Authorization: Bearer <your-auth-token>
```

### Request Body
```json
{
    "menu": "uuid-of-menu",
    "item_name": "Item Name",
    "description": "Item description (optional)",
    "sales_price": "12.99",
    "preparation_time": 15,
    "department": "Kitchen",
    "is_available": true,
    "display_order": 1,
    "image": "image-file (optional)"
}
```

### Field Descriptions
- `menu` (UUID, required): ID of the menu to add the item to
- `item_name` (string, required): Name of the menu item
- `description` (string, optional): Description of the menu item
- `sales_price` (decimal, required): Price of the item (must be > 0)
- `preparation_time` (integer, required): Time in minutes to prepare (must be > 0)
- `department` (string, optional): Kitchen department responsible
- `is_available` (boolean, optional): Whether item is available (default: true)
- `display_order` (integer, optional): Order for displaying in menu (default: 0)
- `image` (file, optional): Image file for the menu item

### Response

#### Success (201 Created)
```json
{
    "message": "Menu item added successfully",
    "menu_item_id": "uuid-of-created-item",
    "item_name": "Item Name"
}
```

#### Error Responses

**403 Forbidden - Not a manager:**
```json
{
    "error": "Only managers can add menu items"
}
```

**403 Forbidden - Wrong restaurant:**
```json
{
    "error": "Cannot add items to menu from different restaurant"
}
```

**400 Bad Request - Validation errors:**
```json
{
    "field_name": ["Error message"]
}
```

### Example Usage

```bash
curl -X POST http://localhost:8000/api/menu/items/add/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token-here" \
  -d '{
    "menu": "123e4567-e89b-12d3-a456-426614174000",
    "item_name": "Grilled Chicken Sandwich",
    "description": "Juicy grilled chicken with fresh vegetables",
    "sales_price": "12.99",
    "preparation_time": 15,
    "department": "Kitchen",
    "is_available": true,
    "display_order": 1
  }'
```