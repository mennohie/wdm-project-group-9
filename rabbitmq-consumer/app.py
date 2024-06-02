import logging
import time
import threading
import requests
from collections import defaultdict
import os
from rabbitMQConsumer import RabbitMQConsumer
import hashlib

GATEWAY_URL = os.environ['GATEWAY_URL']
N_QUEUES = os.environ['MQ_REPLICAS']
REPLICA_INDEX = os.environ['REPLICA_INDEX']


# Example function. You can put RabbitMQ, POST and GET requests to communicate with apps.
def hello_world(hello, world):
    print(f"{hello}, {world}")


def get_queue_for_order(order_id):
    return int(hashlib.md5(order_id.encode()).hexdigest(), 16) % int(N_QUEUES)


def get_request(url):
    while True:
        try:
            response = requests.get(url)
            if response.status_code == 400:
                print("GET request returned status code 400")
                return response, {}
            response_json = response.json()
        except (requests.exceptions.JSONDecodeError, requests.exceptions.ConnectionError):
            print("Target service down. Trying again later...")
            time.sleep(3)
        else:
            break
    return response, response_json


def handle_add_item(order_id, item_id, quantity):
    response, item_details = get_request(f"{GATEWAY_URL}/stock/find/{item_id.strip()}")
    if response.status_code == 200:
        item_details = response.json()
        price = int(item_details['price'])

        add_response = requests.post(
            f"{GATEWAY_URL}/orders/addItemProcess/{order_id.strip()}/{item_id.strip()}/{quantity.strip()}/{price}")
        if add_response.status_code == 200:
            print(f"Item {item_id} added {quantity} times successfully to order {order_id}")
            return True
        else:
            print(
                f"Failed to add item to order, status code: {add_response.status_code}, response: {add_response.text}")
            return False
    else:
        print("Failed to retrieve item details. Item might not exist.")
        return True


def handle_checkout(order_id: str):
    _, order_entry = get_request(f"{GATEWAY_URL}/orders/find/{order_id}")
    user_id, items, total_cost = order_entry["user_id"], order_entry["items"], order_entry["total_cost"]
    print(f"Handling checkout for {order_id}, {items}, User:{user_id}")

    # Calculate the quantity per item
    items_quantities = defaultdict(int)
    for item_id, quantity in items:
        items_quantities[item_id] += quantity

    removed_items = []
    paid = False
    try:
        # Try to pay
        payment_reply = requests.post(f"{GATEWAY_URL}/payment/pay/{user_id}/{total_cost}")
        if payment_reply.status_code != 200:
            print(f"User out of credit: {user_id}")
            return True
        else:
            paid = True

        # Subtract stock for each item
        for item_id, quantity in items_quantities.items():
            stock_reply = requests.post(f"{GATEWAY_URL}/stock/subtract/{item_id}/{quantity}")
            if stock_reply.status_code != 200:
                if paid:
                    rollback_payment(user_id, total_cost)
                rollback_stock(removed_items, order_id)
                print(f"Out of stock on item_id: {item_id}")
                return True

            removed_items.append((item_id, quantity))

        # Update order status to paid
        order_update_reply = requests.post(f"{GATEWAY_URL}/orders/checkoutProcess/{order_id}")
        if order_update_reply.status_code != 200:
            if paid:
                rollback_payment(user_id, total_cost)
            rollback_stock(removed_items, order_id)
            print(f"Failed to update order status: {order_id}")
            return False

        print(f"Checkout handled successfully: {order_id}, calculated queue: {get_queue_for_order(user_id)}")
        return True

    except Exception as e:
        if paid:
            rollback_payment(user_id, total_cost)
        rollback_stock(removed_items, order_id)
        print(f"Failed to handle checkout: {str(e)}")


def rollback_payment(user_id: str, amount: int):
    print(f"Rolling back payment for user: {user_id}. Amount: {amount}")
    response = requests.post(f"{GATEWAY_URL}/payment/add_funds/{user_id}/{amount}")


def rollback_stock(removed_items: list, order_id: str):
    print(f"Rolling back stock for order: {order_id}")
    for item_id, quantity in removed_items:
        print(f"Rollback {item_id} {quantity} times")
        _, current_stock = get_request(f"{GATEWAY_URL}/stock/find/{item_id}")
        current_stock = current_stock["stock"]
        print(f"Stock of {item_id} before rollback: {current_stock}")
        response = requests.post(f"{GATEWAY_URL}/stock/add/{item_id}/{quantity}")
        print(f"Rollback response: {response.status_code}")
        _, current_stock = get_request(f"{GATEWAY_URL}/stock/find/{item_id}")
        current_stock = current_stock["stock"]
        print(f"Stock of {item_id} after rollback: {current_stock}")


consumer = RabbitMQConsumer()

if __name__ == '__main__':
    print("The number of queues is" + str(N_QUEUES))
    queues = [f'main_{REPLICA_INDEX}', f'test_{REPLICA_INDEX}']
    threads = {}

    for q in queues:
        threads[q] = threading.Thread(target=consumer.consume_queue, args=(q, globals()), daemon=True)
        threads[q].start()

    while True:
        # Restart if heartbeat stopped
        for q, t in threads.items():
            if not t.is_alive():
                threads[q] = threading.Thread(target=consumer.consume_queue, args=(q, globals()), daemon=True)
                threads[q].start()

        time.sleep(60)
