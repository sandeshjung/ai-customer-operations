def get_order_tool(order_id: int) -> dict:
    """
    Retrieve order information.

    Args:
        order_id: The ID of the order.
    """
    raise NotImplementedError


def get_shipment_tool(order_id: int) -> dict:
    """
    Retrieve shipment information for an order.

    Args:
        order_id: The order ID.
    """
    raise NotImplementedError


def get_customer_tool(customer_id: int) -> dict:
    """
    Retrieve customer information.

    Args:
        customer_id: The customer ID.
    """
    raise NotImplementedError